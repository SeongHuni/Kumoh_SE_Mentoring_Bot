from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Any

import chromadb

from backend.app.config import Settings
from backend.app.schemas import Source


class ChromaStoreError(RuntimeError):
    """Raised when the configured Chroma collection cannot be read."""


@dataclass(frozen=True)
class IndexState:
    count: int
    compatible: bool
    reason: str


@dataclass(frozen=True)
class RetrievedDocument:
    text: str
    source: Source
    category: str | None


def _metadata_int(metadata: dict[str, Any], key: str) -> int | None:
    value = metadata.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _score(distance: Any) -> float:
    if isinstance(distance, bool) or not isinstance(distance, Real):
        return 0.0
    value = 1.0 - float(distance)
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


class ChromaDataStore:
    def __init__(self, settings: Settings) -> None:
        if not settings.chroma_path.is_dir():
            raise ChromaStoreError(f"Chroma path does not exist: {settings.chroma_path}")
        try:
            client = chromadb.PersistentClient(path=str(settings.chroma_path))
            self.collection = client.get_collection(settings.chroma_collection)
        except Exception as exc:
            raise ChromaStoreError("Configured Chroma collection is unavailable.") from exc
        self.settings = settings

    def inspect(self) -> IndexState:
        try:
            count = self.collection.count()
        except Exception as exc:
            raise ChromaStoreError("Unable to read the Chroma collection.") from exc
        if count == 0:
            return IndexState(count=0, compatible=False, reason="empty_index")

        metadata = self.collection.metadata or {}
        model_matches = metadata.get("embedding_model") == self.settings.embedding_model
        chunk_matches = (
            _metadata_int(metadata, "chunk_size_tokens") == self.settings.chunk_size_tokens
        )
        overlap_matches = (
            _metadata_int(metadata, "chunk_overlap_tokens") == self.settings.chunk_overlap_tokens
        )
        if model_matches and chunk_matches and overlap_matches:
            return IndexState(count=count, compatible=True, reason="compatible")
        return IndexState(count=count, compatible=False, reason="configuration_mismatch")

    def search(
        self,
        embedding: list[float],
        *,
        category: str | None = None,
        limit: int | None = None,
    ) -> list[RetrievedDocument]:
        count = self.collection.count()
        if count == 0:
            return []
        requested_limit = limit or self.settings.top_k
        if requested_limit < 1:
            raise ValueError("Search limit must be greater than zero.")
        try:
            query_kwargs: dict[str, Any] = {
                "query_embeddings": [embedding],
                "n_results": min(requested_limit, count),
                "include": ["documents", "metadatas", "distances"],
            }
            if category:
                query_kwargs["where"] = {"category": category}
            result = self.collection.query(**query_kwargs)
        except Exception as exc:
            raise ChromaStoreError("Chroma similarity search failed.") from exc

        documents = (result.get("documents") or [[]])[0] or []
        metadatas = (result.get("metadatas") or [[]])[0] or []
        distances = (result.get("distances") or [[]])[0] or []
        if not (len(documents) == len(metadatas) == len(distances)):
            raise ChromaStoreError("Chroma returned an invalid query result.")

        retrieved: list[RetrievedDocument] = []
        for document, metadata, distance in zip(documents, metadatas, distances, strict=True):
            values = metadata if isinstance(metadata, dict) else {}
            text = document.strip() if isinstance(document, str) else ""
            if not text:
                continue
            url = str(values.get("source_url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            published_at = str(values.get("published_at") or "").strip() or None
            document_category = str(values.get("category") or "").strip() or None
            retrieved.append(
                RetrievedDocument(
                    text=text,
                    source=Source(
                        title=str(values.get("title") or "Untitled notice"),
                        url=url,
                        source=str(values.get("source") or "Chroma data"),
                        published_at=published_at,
                        score=_score(distance),
                    ),
                    category=document_category,
                )
            )
        return retrieved
