from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

from backend.app.domain import RetrievedChunk

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
SENTENCE_PATTERN = re.compile(r"(?<=[.!?다요])\s+|\n+")
LEADING_TAG_PATTERN = re.compile(r"^\s*\[([^\[\]]+)\]\s*")
DECORATION_PATTERN = re.compile(r"[★☆]+")


class LocalHashProvider:
    """Dependency-free Korean-friendly lexical embeddings and extractive answers."""

    embedding_model = "local-hash-embedding-v1"
    chat_model = "local-extractive-answer-v1"

    def __init__(self, dimensions: int = 1536) -> None:
        if dimensions < 256:
            raise ValueError("dimensions must be at least 256")
        self.dimensions = dimensions

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [token.lower() for token in TOKEN_PATTERN.findall(text)]

    def _features(self, text: str) -> list[tuple[str, float]]:
        tokens = self._tokens(text)
        features: list[tuple[str, float]] = [(f"w:{token}", 2.5) for token in tokens]
        compact = "".join(tokens)
        for size, weight in ((2, 0.7), (3, 1.0), (4, 0.8)):
            features.extend(
                (f"c{size}:{compact[index : index + size]}", weight)
                for index in range(max(0, len(compact) - size + 1))
            )
        title_match = re.search(r"^제목:\s*(.+?)(?:\n|$)", text)
        if title_match:
            title_tokens = self._tokens(title_match.group(1))
            features.extend((f"w:{token}", 6.0) for token in title_tokens)
            title_compact = "".join(title_tokens)
            for size in (2, 3, 4):
                features.extend(
                    (f"c{size}:{title_compact[index : index + size]}", 2.0)
                    for index in range(max(0, len(title_compact) - size + 1))
                )
        return features

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for feature, weight in self._features(text):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector))
        if not norm:
            raise ValueError("임베딩 입력은 비어 있을 수 없습니다.")
        return [value / norm for value in vector]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text.strip()) for text in texts]

    @classmethod
    def _excerpt(cls, text: str, question: str, limit: int = 360) -> str:
        query_tokens = set(cls._tokens(question))
        sentences = [
            sentence.strip()
            for sentence in SENTENCE_PATTERN.split(text)
            if sentence.strip()
        ]
        if not sentences:
            return text[:limit].strip()
        ranked = sorted(
            enumerate(sentences),
            key=lambda item: (
                len(query_tokens.intersection(cls._tokens(item[1]))),
                -item[0],
            ),
            reverse=True,
        )
        best_index = ranked[0][0]
        excerpt = " ".join(sentences[best_index : best_index + 2])
        return excerpt if len(excerpt) <= limit else excerpt[: limit - 1].rstrip() + "…"

    @staticmethod
    def _clean_display_text(value: str) -> str:
        cleaned = DECORATION_PATTERN.sub(" ", value)
        cleaned = re.sub(r"(?<=\S)\[", " [", cleaned)
        cleaned = re.sub(r"\s+([,.;:!?%)\]])", r"\1", cleaned)
        cleaned = re.sub(r"([(\[])\s+", r"\1", cleaned)
        return " ".join(cleaned.split())

    @classmethod
    def _display_title(cls, title: str) -> tuple[str, tuple[str, ...]]:
        categories: list[str] = []
        remainder = title
        while match := LEADING_TAG_PATTERN.match(remainder):
            categories.append(cls._clean_display_text(match.group(1)))
            remainder = remainder[match.end() :]
        cleaned_title = cls._clean_display_text(remainder)
        return cleaned_title or cls._clean_display_text(title), tuple(categories)

    @classmethod
    def _excerpt_points(cls, text: str, question: str) -> tuple[str, ...]:
        excerpt = cls._excerpt(text, question)
        points = tuple(
            cleaned
            for part in DECORATION_PATTERN.split(excerpt)
            if (cleaned := cls._clean_display_text(part))
        )
        return points or (cls._clean_display_text(excerpt),)

    def answer(self, question: str, contexts: Sequence[RetrievedChunk]) -> str:
        lines = ["확인한 최신 공지"]
        seen_urls: set[str] = set()
        source_number = 0
        for item in contexts:
            if item.chunk.url in seen_urls:
                continue
            seen_urls.add(item.chunk.url)
            source_number += 1
            title, categories = self._display_title(item.chunk.title)
            lines.extend(("", f"{source_number}. {title}"))
            if categories:
                lines.append(f"분류 · {' · '.join(categories)}")
            lines.extend(
                (
                    f"게시일 · {item.chunk.published_at or '게시일 미상'}",
                    "",
                    "핵심 내용",
                )
            )
            lines.extend(
                f"- {point}"
                for point in self._excerpt_points(item.chunk.text, question)
            )
            lines.append(f"출처 · [자료 {source_number}]")
            if source_number >= 3:
                break
        lines.extend(
            (
                "",
                "원문 확인",
                "- 신청 가능 여부와 마감일은 아래 원문 공지에서 다시 확인해 주세요.",
            )
        )
        return "\n".join(lines)
