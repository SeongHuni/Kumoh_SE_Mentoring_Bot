from dataclasses import FrozenInstanceError

import pytest
from backend.app.domain import TextChunk
from backend.app.lexical_retriever import BM25Retriever, LexicalResult


def make_chunk(
    chunk_id: str,
    title: str,
    text: str,
    *,
    intent_key: str = "registration.main",
) -> TextChunk:
    return TextChunk(
        id=chunk_id,
        post_id=f"post-{chunk_id}",
        source="kumoh",
        title=title,
        text=text,
        url=f"https://kumoh.example/{chunk_id}",
        published_at="2026-07-16",
        chunk_index=0,
        topic_key="registration",
        topic_label="수강신청",
        is_latest_topic=True,
        intent_key=intent_key,
    )


def registration_chunk() -> TextChunk:
    return make_chunk(
        "registration-main",
        "2026학년도 수강신청 일정 안내",
        "최근 수강신청 기간과 신청 방법, 수강정정 일정을 안내합니다.",
    )


def attendance_chunk() -> TextChunk:
    return make_chunk(
        "registration-attendance",
        "2026 조기취업자 출석인정 신청 안내",
        "조기취업자의 출석인정 신청과 증빙서류 제출 방법을 안내합니다.",
        intent_key="registration.attendance",
    )


def test_exact_registration_main_ranks_above_newer_attendance_notice() -> None:
    retriever = BM25Retriever([attendance_chunk(), registration_chunk()])

    results = retriever.search(["최근 수강신청 공지"], top_k=2)

    assert results[0].chunk.intent_key == "registration.main"
    assert [result.rank for result in results] == [1, 2]


def test_result_preserves_chunk_metadata_and_has_frozen_contract() -> None:
    chunk = registration_chunk()
    result = BM25Retriever([chunk]).search(["수강신청"], top_k=1)[0]

    assert isinstance(result, LexicalResult)
    assert result.chunk is chunk
    assert result.chunk.model_dump() == chunk.model_dump()
    with pytest.raises(FrozenInstanceError):
        result.rank = 2  # type: ignore[misc]


def test_ranking_is_deterministic_by_score_then_chunk_id() -> None:
    first = make_chunk("b-id", "수강신청 공지", "수강신청 공지")
    second = make_chunk("a-id", "수강신청 공지", "수강신청 공지")
    retriever = BM25Retriever([first, second])

    first_run = retriever.search(["수강신청"], top_k=2)
    second_run = retriever.search(["수강신청"], top_k=2)

    assert [item.chunk.id for item in first_run] == ["a-id", "b-id"]
    assert first_run == second_run


def test_korean_spacing_matches_compact_form() -> None:
    spaced = make_chunk("spaced", "수강 신청 안내", "수강 신청 기간을 확인하세요.")
    unrelated = make_chunk(
        "unrelated",
        "장학금 신청 안내",
        "장학금 신청 기간입니다.",
        intent_key="scholarship.general",
    )

    results = BM25Retriever([unrelated, spaced]).search(["수강신청"], top_k=1)

    assert [result.chunk.id for result in results] == ["spaced"]


def test_search_ignores_blank_variants_and_excludes_zero_scores() -> None:
    chunk = registration_chunk()
    retriever = BM25Retriever([chunk])

    assert retriever.search(["", "   ", "수강신청"], top_k=1)[0].chunk is chunk
    assert retriever.search(["존재하지 않는 단어"], top_k=1) == []
    assert BM25Retriever([]).search(["수강신청"], top_k=1) == []
    assert retriever.search([], top_k=1) == []


@pytest.mark.parametrize("top_k", [0, -1, True])
def test_top_k_must_be_a_positive_integer(top_k: int) -> None:
    with pytest.raises(ValueError, match="top_k"):
        BM25Retriever([registration_chunk()]).search(["수강신청"], top_k=top_k)
