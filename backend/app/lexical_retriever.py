from __future__ import annotations

import math
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from backend.app.domain import TextChunk

K1 = 1.5
B = 0.75


@dataclass(frozen=True)
class LexicalResult:
    chunk: TextChunk
    score: float
    rank: int


def _tokenize(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    tokens: list[str] = []
    current: list[str] = []
    for character in normalized:
        if character.isalnum():
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))

    features = list(tokens)
    for token in tokens:
        features.extend(
            token[index : index + size]
            for size in (2, 3, 4)
            for index in range(len(token) - size + 1)
        )
    for left, right in zip(tokens, tokens[1:], strict=False):
        features.extend(
            left[-left_size:] + right[:right_size]
            for left_size in range(1, min(4, len(left)) + 1)
            for right_size in range(1, min(4, len(right)) + 1)
            if 2 <= left_size + right_size <= 4
        )
    return tuple(features)


class BM25Retriever:
    def __init__(self, chunks: Sequence[TextChunk]) -> None:
        self.chunks = tuple(chunks)
        if len({chunk.id for chunk in self.chunks}) != len(self.chunks):
            raise ValueError("chunk ids must be unique")
        self._document_terms = tuple(
            Counter(_tokenize(f"{chunk.title} {chunk.text}")) for chunk in self.chunks
        )
        self._document_lengths = tuple(sum(terms.values()) for terms in self._document_terms)
        self._document_frequency: Counter[str] = Counter()
        for terms in self._document_terms:
            self._document_frequency.update(terms.keys())
        self._avgdl = (
            sum(self._document_lengths) / len(self._document_lengths)
            if self._document_lengths
            else 0.0
        )
        self._idf = {
            term: math.log(
                1.0
                + (len(self.chunks) - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            for term, document_frequency in self._document_frequency.items()
        }

    def _score_document(self, document_index: int, query_terms: Sequence[str]) -> float:
        unique_query_terms = set(query_terms)
        if not unique_query_terms or self._avgdl == 0.0:
            return 0.0

        document_terms = self._document_terms[document_index]
        document_length = self._document_lengths[document_index]
        score = 0.0
        for term in unique_query_terms:
            document_frequency = document_terms.get(term, 0)
            if not document_frequency:
                continue
            denominator = document_frequency + K1 * (
                1.0 - B + B * document_length / self._avgdl
            )
            score += (
                self._idf.get(term, 0.0)
                * document_frequency
                * (K1 + 1.0)
                / denominator
            )
        return score

    def search(self, queries: Sequence[str], top_k: int) -> list[LexicalResult]:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        if not self.chunks:
            return []

        query_variants = tuple(dict.fromkeys(query for query in queries if query.strip()))
        tokenized_queries = tuple(_tokenize(query) for query in query_variants)
        if not tokenized_queries:
            return []

        scored = [
            (chunk, max(self._score_document(index, query) for query in tokenized_queries))
            for index, chunk in enumerate(self.chunks)
        ]
        ordered = sorted(
            ((chunk, score) for chunk, score in scored if score > 0),
            key=lambda item: (-item[1], item[0].id),
        )
        return [
            LexicalResult(chunk=chunk, score=score, rank=rank)
            for rank, (chunk, score) in enumerate(ordered[:top_k], start=1)
        ]
