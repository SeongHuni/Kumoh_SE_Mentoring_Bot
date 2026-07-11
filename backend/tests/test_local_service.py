from backend.app.domain import RetrievedChunk, TextChunk
from backend.app.local_service import LocalHashProvider


def test_local_embeddings_are_deterministic_and_normalized() -> None:
    provider = LocalHashProvider(dimensions=256)

    first = provider.embed(["수강신청 기간 안내"])[0]
    second = provider.embed(["수강신청 기간 안내"])[0]

    assert first == second
    assert abs(sum(value * value for value in first) - 1.0) < 1e-6


def test_local_answer_contains_source_marker() -> None:
    provider = LocalHashProvider(dimensions=256)
    context = RetrievedChunk(
        chunk=TextChunk(
            id="kumoh:1:0",
            post_id="1",
            source="kumoh",
            title="수강신청 안내",
            text="수강신청 변경 기간은 3월 4일까지입니다. 통합정보시스템에서 신청합니다.",
            url="https://example.com/1",
            published_at="2026-02-20",
            chunk_index=0,
        ),
        score=0.8,
    )

    answer = provider.answer("수강신청은 어디서 해?", [context])

    assert "통합정보시스템" in answer
    assert "[자료 1]" in answer
