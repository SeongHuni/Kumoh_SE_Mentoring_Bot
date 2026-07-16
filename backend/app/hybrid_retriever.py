from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import inf

from backend.app.domain import TextChunk
from backend.app.lexical_retriever import BM25Retriever, LexicalResult
from backend.app.openai_service import AIProvider
from backend.app.query_planner import QueryPlan
from backend.app.vector_store import ChromaVectorStore


@dataclass(frozen=True)
class DenseResult:
    chunk: TextChunk
    score: float
    rank: int


@dataclass(frozen=True)
class HybridCandidate:
    chunk: TextChunk
    dense_score: float
    lexical_score: float
    dense_rank: int | None
    lexical_rank: int | None
    fused_score: float

    @property
    def signal_count(self) -> int:
        return int(self.dense_rank is not None) + int(self.lexical_rank is not None)


def _validate_positive_integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def reciprocal_rank(rank: int | None, k: int = 60) -> float:
    if rank is not None:
        _validate_positive_integer(rank, "rank")
    _validate_positive_integer(k, "k")
    return 0.0 if rank is None else 1.0 / (k + rank)


def _same_chunk(left: TextChunk, right: TextChunk) -> bool:
    return left.model_dump() == right.model_dump()


def _merge_result(
    entries: dict[str, tuple[TextChunk, float, int]],
    chunk: TextChunk,
    score: float,
    rank: int,
) -> None:
    existing = entries.get(chunk.id)
    if existing is not None and not _same_chunk(existing[0], chunk):
        raise ValueError(f"conflicting metadata for chunk id {chunk.id!r}")
    if existing is None:
        entries[chunk.id] = (chunk, score, rank)
        return
    best_score = max(existing[1], score)
    best_rank = min(existing[2], rank)
    entries[chunk.id] = (existing[0], best_score, best_rank)


def fuse_results(
    lexical: Sequence[LexicalResult],
    dense: Sequence[DenseResult],
    k: int = 60,
) -> list[HybridCandidate]:
    _validate_positive_integer(k, "k")
    lexical_entries: dict[str, tuple[TextChunk, float, int]] = {}
    dense_entries: dict[str, tuple[TextChunk, float, int]] = {}
    for result in lexical:
        _validate_positive_integer(result.rank, "rank")
        _merge_result(
            lexical_entries,
            result.chunk,
            result.score,
            result.rank,
        )
    for result in dense:
        _validate_positive_integer(result.rank, "rank")
        _merge_result(dense_entries, result.chunk, result.score, result.rank)

    candidates: list[HybridCandidate] = []
    for chunk_id in sorted(set(lexical_entries) | set(dense_entries)):
        lexical_entry = lexical_entries.get(chunk_id)
        dense_entry = dense_entries.get(chunk_id)
        if lexical_entry is not None and dense_entry is not None:
            if not _same_chunk(lexical_entry[0], dense_entry[0]):
                raise ValueError(f"conflicting metadata for chunk id {chunk_id!r}")
        selected = lexical_entry or dense_entry
        assert selected is not None
        candidates.append(
            HybridCandidate(
                chunk=selected[0],
                dense_score=dense_entry[1] if dense_entry is not None else 0.0,
                lexical_score=lexical_entry[1] if lexical_entry is not None else 0.0,
                dense_rank=dense_entry[2] if dense_entry is not None else None,
                lexical_rank=lexical_entry[2] if lexical_entry is not None else None,
                fused_score=reciprocal_rank(
                    dense_entry[2] if dense_entry is not None else None,
                    k,
                )
                + reciprocal_rank(
                    lexical_entry[2] if lexical_entry is not None else None,
                    k,
                ),
            )
        )
    return sorted(
        candidates,
        key=lambda item: (
            -item.fused_score,
            -item.signal_count,
            item.dense_rank if item.dense_rank is not None else inf,
            item.lexical_rank if item.lexical_rank is not None else inf,
            -item.dense_score,
            -item.lexical_score,
            item.chunk.id,
        ),
    )


class HybridRetriever:
    def __init__(
        self,
        provider: AIProvider,
        vector_store: ChromaVectorStore,
        lexical_top_k: int,
        dense_top_k: int,
    ) -> None:
        _validate_positive_integer(lexical_top_k, "lexical_top_k")
        _validate_positive_integer(dense_top_k, "dense_top_k")
        self.provider = provider
        self.vector_store = vector_store
        self.lexical_top_k = lexical_top_k
        self.dense_top_k = dense_top_k

    def retrieve(self, plan: QueryPlan, *, topic_key: str) -> list[HybridCandidate]:
        if not isinstance(topic_key, str) or not topic_key.strip():
            raise ValueError("topic_key must not be blank")
        where = {"topic_key": topic_key}
        corpus = self.vector_store.list_chunks(where=where)
        if not corpus:
            return []

        lexical_results = BM25Retriever(corpus).search(plan.queries, self.lexical_top_k)
        embeddings = self.provider.embed(plan.queries)
        if len(embeddings) != len(plan.queries):
            raise ValueError("embedding count must match query count")

        dense_by_id: dict[str, tuple[TextChunk, float]] = {}
        for embedding in embeddings:
            for retrieved in self.vector_store.query(
                embedding,
                self.dense_top_k,
                where=where,
            ):
                existing = dense_by_id.get(retrieved.chunk.id)
                if existing is not None and not _same_chunk(existing[0], retrieved.chunk):
                    raise ValueError(
                        f"conflicting metadata for chunk id {retrieved.chunk.id!r}"
                    )
                if existing is None or retrieved.score > existing[1]:
                    dense_by_id[retrieved.chunk.id] = (retrieved.chunk, retrieved.score)

        dense_results = [
            DenseResult(chunk=chunk, score=score, rank=rank)
            for rank, (chunk, score) in enumerate(
                sorted(dense_by_id.values(), key=lambda item: (-item[1], item[0].id)),
                start=1,
            )
        ]
        return fuse_results(lexical_results, dense_results)
