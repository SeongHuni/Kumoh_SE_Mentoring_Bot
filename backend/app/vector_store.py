from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import chromadb

from backend.app.domain import RetrievedChunk, TextChunk


def _chunk_metadata(chunk: TextChunk) -> dict[str, str | int | bool]:
    metadata: dict[str, str | int | bool] = {
        "post_id": chunk.post_id,
        "source": chunk.source,
        "title": chunk.title,
        "url": chunk.url,
        "published_at": chunk.published_at or "",
        "chunk_index": chunk.chunk_index,
        "topic_key": chunk.topic_key,
        "topic_label": chunk.topic_label,
        "is_latest_topic": chunk.is_latest_topic,
    }
    if chunk.intent_key is not None:
        metadata["intent_key"] = chunk.intent_key
    return metadata


def _text_chunk(
    chunk_id: str,
    document: str | None,
    metadata: dict[str, object] | None,
) -> TextChunk:
    values = metadata or {}
    if not isinstance(values, dict):
        raise ValueError("Chroma metadata must be an object.")
    return TextChunk(
        id=chunk_id,
        post_id=str(values.get("post_id", "")),
        source=str(values.get("source", "unknown")),
        title=str(values.get("title", "제목 없음")),
        text=document or "",
        url=str(values.get("url", "")),
        published_at=str(values.get("published_at") or "") or None,
        chunk_index=int(values.get("chunk_index", 0)),
        topic_key=str(values.get("topic_key", "general")),
        topic_label=str(values.get("topic_label", "전체 공지")),
        is_latest_topic=bool(values.get("is_latest_topic", False)),
        intent_key=str(values.get("intent_key") or "") or None,
    )


def _result_array(result: dict[str, object], key: str, *, nested: bool) -> list[object]:
    value = result.get(key)
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"Chroma result array {key!r} is malformed.")
    if nested:
        if not value:
            return []
        if len(value) != 1:
            raise ValueError(f"Chroma result array {key!r} must contain one query row.")
        value = value[0]
        if value is None:
            return []
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ValueError(f"Chroma result array {key!r} is malformed.")
    return list(value)


def _validate_result_lengths(arrays: dict[str, list[object]]) -> int:
    lengths = {key: len(value) for key, value in arrays.items()}
    if not lengths:
        return 0
    distinct_lengths = set(lengths.values())
    if len(distinct_lengths) != 1:
        detail = ", ".join(f"{key}={length}" for key, length in lengths.items())
        raise ValueError(f"Chroma result arrays have mismatched lengths: {detail}")
    return next(iter(distinct_lengths))


class ChromaVectorStore:
    def __init__(self, path: Path, collection_name: str) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(path))
        self.collection_name = collection_name
        self.collection = self._get_or_create()

    def _get_or_create(self):
        return self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def reset(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception as exc:  # Chroma versions expose different not-found errors.
            if "does not exist" not in str(exc).lower() and "not found" not in str(exc).lower():
                raise
        self.collection = self._get_or_create()

    def count(self) -> int:
        return self.collection.count()

    def list_chunks(self, where: dict[str, object] | None = None) -> list[TextChunk]:
        get_kwargs: dict[str, object] = {"include": ["documents", "metadatas"]}
        if where is not None:
            get_kwargs["where"] = where
        result = self.collection.get(**get_kwargs)
        arrays = {
            key: _result_array(result, key, nested=False)
            for key in ("ids", "documents", "metadatas")
        }
        row_count = _validate_result_lengths(arrays)
        return [
            _text_chunk(
                chunk_id=str(arrays["ids"][index]),
                document=arrays["documents"][index],
                metadata=arrays["metadatas"][index],
            )
            for index in range(row_count)
        ]

    def upsert(self, chunks: Sequence[TextChunk], embeddings: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("청크 수와 임베딩 수가 일치하지 않습니다.")
        if not chunks:
            return
        self.collection.upsert(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            embeddings=[list(vector) for vector in embeddings],
            metadatas=[_chunk_metadata(chunk) for chunk in chunks],
        )

    def query(
        self,
        embedding: Sequence[float],
        top_k: int,
        where: dict[str, object] | None = None,
    ) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        query_kwargs: dict[str, object] = {
            "query_embeddings": [list(embedding)],
            "n_results": min(top_k, self.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if where is not None:
            query_kwargs["where"] = where
        result = self.collection.query(**query_kwargs)
        arrays = {
            key: _result_array(result, key, nested=True)
            for key in ("ids", "documents", "metadatas", "distances")
        }
        row_count = _validate_result_lengths(arrays)
        retrieved: list[RetrievedChunk] = []
        for index in range(row_count):
            retrieved.append(
                RetrievedChunk(
                    chunk=_text_chunk(
                        chunk_id=str(arrays["ids"][index]),
                        document=arrays["documents"][index],
                        metadata=arrays["metadatas"][index],
                    ),
                    score=max(
                        0.0,
                        min(1.0, 1.0 - float(arrays["distances"][index])),
                    ),
                )
            )
        return retrieved
