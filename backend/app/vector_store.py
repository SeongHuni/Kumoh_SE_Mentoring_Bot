from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import chromadb

from backend.app.domain import RetrievedChunk, TextChunk


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

    def upsert(self, chunks: Sequence[TextChunk], embeddings: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("청크 수와 임베딩 수가 일치하지 않습니다.")
        if not chunks:
            return
        self.collection.upsert(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            embeddings=[list(vector) for vector in embeddings],
            metadatas=[
                {
                    "post_id": chunk.post_id,
                    "source": chunk.source,
                    "title": chunk.title,
                    "url": chunk.url,
                    "published_at": chunk.published_at or "",
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in chunks
            ],
        )

    def query(self, embedding: Sequence[float], top_k: int) -> list[RetrievedChunk]:
        if self.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[list(embedding)],
            n_results=min(top_k, self.count()),
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        retrieved: list[RetrievedChunk] = []
        for chunk_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=True
        ):
            metadata = metadata or {}
            retrieved.append(
                RetrievedChunk(
                    chunk=TextChunk(
                        id=chunk_id,
                        post_id=str(metadata.get("post_id", "")),
                        source=str(metadata.get("source", "unknown")),
                        title=str(metadata.get("title", "제목 없음")),
                        text=document or "",
                        url=str(metadata.get("url", "")),
                        published_at=str(metadata.get("published_at") or "") or None,
                        chunk_index=int(metadata.get("chunk_index", 0)),
                    ),
                    score=max(0.0, min(1.0, 1.0 - float(distance))),
                )
            )
        return retrieved
