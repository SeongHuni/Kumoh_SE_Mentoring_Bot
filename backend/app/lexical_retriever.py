from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from backend.app.domain import TextChunk

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
K1 = 1.5
B = 0.75


@dataclass(frozen=True)
class LexicalResult:
    chunk: TextChunk
    score: float
    rank: int


def _tokenize(value: str) -> tuple[str, ...]:
    tokens = tuple(token.casefold() for token in TOKEN_PATTERN.findall(value))
    compact = "".join(tokens)
    ngrams = tuple(
        compact[index : index + size]
        for size in (2, 3, 4)
        for index in range(len(compact) - size + 1)
    )
    return tokens + ngrams


class BM25Retriever:
    def __init__(self, chunks: Sequence[TextChunk]) -> None:
        self.chunks = tuple(chunks)
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

    def _score_document(self, document_index: int, query: str) -> float:
        query_terms = Counter(_tokenize(query))
        if not query_terms or self._avgdl == 0.0:
            return 0.0

        document_terms = self._document_terms[document_index]
        document_length = self._document_lengths[document_index]
        score = 0.0
        for term, query_frequency in query_terms.items():
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
                * query_frequency
            )
        return score

    def search(self, queries: Sequence[str], top_k: int) -> list[LexicalResult]:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        if not self.chunks:
            return []

        query_variants = tuple(query for query in queries if query.strip())
        if not query_variants:
            return []

        scored = [
            (chunk, max(self._score_document(index, query) for query in query_variants))
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
