from dataclasses import FrozenInstanceError

import pytest
from backend.app.domain import RetrievedChunk, TextChunk
from backend.app.hybrid_retriever import (
    DenseResult,
    HybridRetriever,
    fuse_results,
    reciprocal_rank,
)
from backend.app.lexical_retriever import LexicalResult
from backend.app.query_planner import QueryPlan


def make_chunk(
    chunk_id: str,
    title: str,
    text: str,
    *,
    intent_key: str = "registration.main",
    is_latest_topic: bool = True,
) -> TextChunk:
    return TextChunk(
        id=chunk_id,
        post_id=f"post-{chunk_id}",
        source="kumoh",
        title=title,
        text=text,
        url=f"https://example.com/{chunk_id}",
        published_at="2026-07-16",
        chunk_index=0,
        topic_key="registration",
        topic_label="수강신청",
        is_latest_topic=is_latest_topic,
        intent_key=intent_key,
    )


def lexical(chunk: TextChunk, *, score: float, rank: int) -> LexicalResult:
    return LexicalResult(chunk=chunk, score=score, rank=rank)


def dense(chunk: TextChunk, *, score: float, rank: int) -> DenseResult:
    return DenseResult(chunk=chunk, score=score, rank=rank)


def test_rrf_preserves_independent_rank_evidence() -> None:
    main = make_chunk("main", "수강신청", "수강신청 일정")
    attendance = make_chunk(
        "attendance",
        "출석인정",
        "조기취업자 출석인정",
        intent_key="registration.attendance",
    )

    results = fuse_results(
        lexical=[lexical(main, score=4.0, rank=1)],
        dense=[dense(main, score=0.8, rank=2), dense(attendance, score=0.9, rank=1)],
    )

    candidate = next(item for item in results if item.chunk.id == "main")
    assert candidate.lexical_rank == 1
    assert candidate.dense_rank == 2
    assert candidate.signal_count == 2
    assert candidate.fused_score == reciprocal_rank(1) + reciprocal_rank(2)


def test_hybrid_types_are_frozen_and_rrf_rejects_nonpositive_values() -> None:
    chunk = make_chunk("one", "공지", "본문")
    result = DenseResult(chunk=chunk, score=0.5, rank=1)

    assert isinstance(result, DenseResult)
    with pytest.raises(FrozenInstanceError):
        result.rank = 2  # type: ignore[misc]
    with pytest.raises(ValueError):
        reciprocal_rank(0)
    with pytest.raises(ValueError):
        reciprocal_rank(1, k=0)


def test_fuse_duplicate_entries_choose_best_signal_and_reject_conflicting_metadata() -> None:
    chunk = make_chunk("one", "공지", "본문")
    duplicate = lexical(chunk, score=0.9, rank=1)
    weaker = lexical(chunk, score=0.4, rank=3)

    result = fuse_results([weaker, duplicate], [dense(chunk, score=0.7, rank=2)])[0]

    assert result.lexical_rank == 1
    assert result.lexical_score == 0.9
    assert result.chunk is chunk

    conflicting = make_chunk("one", "다른 제목", "본문")
    with pytest.raises(ValueError, match="conflicting metadata"):
        fuse_results([duplicate], [dense(conflicting, score=0.7, rank=2)])


class FakeProvider:
    def __init__(self, embeddings: list[list[float]] | None = None) -> None:
        self.embeddings = embeddings or [[1.0], [2.0]]
        self.embed_calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls.append(texts)
        return self.embeddings


class FakeVectorStore:
    def __init__(self, chunks: list[TextChunk], dense_results: list[list[RetrievedChunk]]) -> None:
        self.chunks = chunks
        self.dense_results = dense_results
        self.list_calls: list[dict[str, object] | None] = []
        self.query_calls: list[tuple[list[float], int, dict[str, object] | None]] = []

    def list_chunks(self, where: dict[str, object] | None = None) -> list[TextChunk]:
        self.list_calls.append(where)
        return self.chunks

    def query(
        self,
        embedding: list[float],
        top_k: int,
        where: dict[str, object] | None = None,
    ) -> list[RetrievedChunk]:
        self.query_calls.append((embedding, top_k, where))
        return self.dense_results[len(self.query_calls) - 1]


def test_retrieve_uses_all_topic_chunks_and_global_dense_ranks() -> None:
    main = make_chunk(
        "main",
        "2026 수강신청 일정 안내",
        "최근 수강신청 기간과 신청 방법",
        is_latest_topic=False,
    )
    attendance = make_chunk(
        "attendance",
        "조기취업자 출석인정 신청 안내",
        "출석인정 신청과 증빙서류 제출",
        intent_key="registration.attendance",
        is_latest_topic=True,
    )
    provider = FakeProvider()
    store = FakeVectorStore(
        [main, attendance],
        [
            [RetrievedChunk(chunk=main, score=0.8), RetrievedChunk(chunk=attendance, score=0.2)],
            [RetrievedChunk(chunk=main, score=0.9), RetrievedChunk(chunk=attendance, score=0.95)],
        ],
    )
    plan = QueryPlan(
        original="수강신청 일정",
        queries=("수강신청 일정", "출석인정 신청"),
        hypothetical_notice="공지",
    )

    results = HybridRetriever(provider, store, lexical_top_k=2, dense_top_k=2).retrieve(
        plan,
        topic_key="registration",
    )

    assert provider.embed_calls == [plan.queries]
    assert store.list_calls == [{"topic_key": "registration"}]
    assert len(store.query_calls) == 2
    assert all(call[2] == {"topic_key": "registration"} for call in store.query_calls)
    assert all("is_latest_topic" not in (call[2] or {}) for call in store.query_calls)
    by_id = {item.chunk.id: item for item in results}
    assert set(by_id) == {"main", "attendance"}
    assert by_id["attendance"].dense_rank == 1
    assert by_id["main"].dense_rank == 2
    assert by_id["main"].lexical_rank is not None
    assert by_id["main"].chunk.intent_key == "registration.main"


def test_retrieve_without_topic_scope_uses_the_entire_corpus() -> None:
    main = make_chunk("main", "2026 수강신청 일정 안내", "수강신청 기간")
    provider = FakeProvider()
    store = FakeVectorStore(
        [main],
        [
            [RetrievedChunk(chunk=main, score=0.9)],
            [RetrievedChunk(chunk=main, score=0.8)],
        ],
    )
    plan = QueryPlan("최근 학과 공지", ("최근 학과 공지", "전체 공지"), "공지")

    results = HybridRetriever(provider, store, lexical_top_k=1, dense_top_k=1).retrieve(
        plan,
        topic_key=None,
    )

    assert [item.chunk.id for item in results] == ["main"]
    assert store.list_calls == [None]
    assert all(call[2] is None for call in store.query_calls)


def test_retrieve_fails_closed_for_empty_corpus_without_embedding_or_dense_calls() -> None:
    provider = FakeProvider()
    store = FakeVectorStore([], [])
    plan = QueryPlan("질문", ("질문",), "공지")

    assert HybridRetriever(provider, store, lexical_top_k=1, dense_top_k=1).retrieve(
        plan,
        topic_key="registration",
    ) == []
    assert provider.embed_calls == []
    assert store.query_calls == []


def test_retrieve_rejects_blank_topic_and_embedding_count_mismatch() -> None:
    provider = FakeProvider(embeddings=[[1.0]])
    store = FakeVectorStore([make_chunk("one", "공지", "본문")], [[]])
    plan = QueryPlan("질문", ("질문", "확장 질문"), "공지")
    retriever = HybridRetriever(provider, store, lexical_top_k=1, dense_top_k=1)

    with pytest.raises(ValueError, match="topic_key"):
        retriever.retrieve(plan, topic_key=" ")
    with pytest.raises(ValueError, match="embedding count"):
        retriever.retrieve(plan, topic_key="registration")
    assert store.query_calls == []


@pytest.mark.parametrize(
    ("lexical_top_k", "dense_top_k"),
    [(0, 1), (1, 0), (True, 1)],
)
def test_retriever_rejects_nonpositive_top_k(lexical_top_k: int, dense_top_k: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        HybridRetriever(FakeProvider(), FakeVectorStore([], []), lexical_top_k, dense_top_k)
