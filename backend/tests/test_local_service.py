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
            topic_key="general",
            topic_label="전체 공지",
            is_latest_topic=False,
        ),
        score=0.8,
    )

    answer = provider.answer("수강신청은 어디서 해?", [context])

    assert "통합정보시스템" in answer
    assert "[자료 1]" in answer
    assert "수강신청 안내" in answer
    assert "2026-02-20" in answer
    assert "확인된 공지" in answer


def test_local_answer_uses_only_context_facts_and_readable_sections() -> None:
    provider = LocalHashProvider(dimensions=256)
    context = RetrievedChunk(
        chunk=TextChunk(
            id="kumoh:2:0",
            post_id="2",
            source="kumoh",
            title="캡스톤디자인 신청 안내",
            text="신청서는 학과 사무실에 제출합니다. 제출 기한은 3월 20일입니다.",
            url="https://example.com/2",
            published_at="2026-03-01",
            chunk_index=0,
            topic_key="capstone",
            topic_label="캡스톤디자인",
            is_latest_topic=True,
            intent_key="capstone.general",
        ),
        score=0.8,
    )

    answer = provider.answer("캡스톤디자인은 어떻게 신청해?", [context])

    assert "1. 캡스톤디자인 신청 안내" in answer
    assert "학과 사무실" in answer
    assert "3월 20일" in answer
    assert "등록금" not in answer
    assert answer.index("캡스톤디자인 신청 안내") < answer.index("[자료 1]")
