from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from backend.app.domain import RetrievedChunk

_BODY_DELIMITER = re.compile(r"본문\s*:")
_SENTENCE_ENDINGS = frozenset(".!?")


def _normalized_alphanumeric(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    tokens: list[str] = []
    current: list[str] = []
    for character in normalized:
        if character.isalnum():
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current.clear()
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


def _valid_items(items: Sequence[RetrievedChunk]) -> tuple[RetrievedChunk, ...]:
    if isinstance(items, (str, bytes, bytearray)) or not isinstance(items, Sequence):
        raise TypeError("items must be a sequence of RetrievedChunk")
    validated = tuple(items)
    if not all(isinstance(item, RetrievedChunk) for item in validated):
        raise TypeError("items must be a sequence of RetrievedChunk")
    return validated


def _valid_terms(terms: Sequence[str]) -> tuple[str, ...]:
    if isinstance(terms, (str, bytes, bytearray)) or not isinstance(terms, Sequence):
        raise TypeError("terms must be a sequence of strings")
    normalized: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if not isinstance(term, str):
            raise TypeError("terms must be a sequence of strings")
        compact = _normalized_alphanumeric(term)
        if len(compact) < 2 or compact in seen:
            continue
        seen.add(compact)
        normalized.append(compact)
    return tuple(normalized)


def _body(text: str) -> str:
    delimiter = _BODY_DELIMITER.search(text)
    return text[delimiter.end() :].lstrip() if delimiter is not None else text


def _sentences(text: str) -> list[str]:
    found: list[str] = []
    current: list[str] = []

    def emit() -> None:
        sentence = "".join(current).strip()
        current.clear()
        if sentence:
            found.append(sentence)

    for character in text:
        if character in _SENTENCE_ENDINGS:
            current.append(character)
            emit()
        elif character in "\r\n":
            emit()
        else:
            current.append(character)
    emit()
    return found


def _unique_sentences(sentences: Sequence[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        key = _normalized_alphanumeric(sentence)
        if not key:
            key = "".join(unicodedata.normalize("NFKC", sentence).casefold().split())
        if key not in seen:
            seen.add(key)
            unique.append(sentence)
    return unique


def _term_match_quality(sentence_tokens: tuple[str, ...], term: str) -> int:
    for start in range(len(sentence_tokens)):
        candidate = ""
        for token in sentence_tokens[start:]:
            candidate += token
            if candidate == term:
                return 2
            if candidate.startswith(term):
                return 1
            if len(candidate) >= len(term):
                break
    return 0


def compress_contexts(
    items: Sequence[RetrievedChunk],
    terms: Sequence[str],
    *,
    max_sentences: int = 3,
) -> list[RetrievedChunk]:
    if isinstance(max_sentences, bool) or not isinstance(max_sentences, int) or max_sentences < 1:
        raise ValueError("max_sentences must be a positive integer")

    validated_items = _valid_items(items)
    valid_terms = _valid_terms(terms)
    if not valid_terms:
        return list(validated_items)

    compressed: list[RetrievedChunk] = []
    for item in validated_items:
        sentences = _unique_sentences(_sentences(_body(item.chunk.text)))
        candidates: list[tuple[int, str, int, int, int, float, int]] = []
        for index, sentence in enumerate(sentences):
            sentence_tokens = _tokens(sentence)
            matched_terms = tuple(
                (term, _term_match_quality(sentence_tokens, term))
                for term in valid_terms
            )
            matched_terms = tuple(
                (term, quality) for term, quality in matched_terms if quality
            )
            if not matched_terms:
                continue
            term_length = sum(len(term) for term, _ in matched_terms)
            match_quality = sum(quality for _, quality in matched_terms)
            sentence_length = len(_normalized_alphanumeric(sentence))
            density = term_length / sentence_length if sentence_length else 0.0
            candidates.append(
                (
                    index,
                    sentence,
                    len(matched_terms),
                    term_length,
                    match_quality,
                    density,
                    sentence_length,
                )
            )

        if not candidates:
            compressed.append(item)
            continue

        selected = sorted(
            candidates,
            key=lambda candidate: (
                -candidate[2],
                -candidate[3],
                -candidate[4],
                -candidate[5],
                candidate[6],
                candidate[0],
            ),
        )[:max_sentences]
        selected_text = "\n".join(
            sentence
            for _, sentence, _, _, _, _, _ in sorted(selected, key=lambda candidate: candidate[0])
        )
        compressed.append(
            item.model_copy(
                update={"chunk": item.chunk.model_copy(update={"text": selected_text})}
            )
        )
    return compressed
