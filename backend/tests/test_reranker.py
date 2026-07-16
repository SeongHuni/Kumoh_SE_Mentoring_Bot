from dataclasses import FrozenInstanceError

import pytest
from backend.app.domain import TextChunk
from backend.app.hybrid_retriever import HybridCandidate
from backend.app.intent_analysis import IntentOption
from backend.app.query_intent import QueryIntent
from backend.app.reranker import RerankedCandidate, rerank
from backend.app.topic_rules import IntentRule


def make_chunk(
    chunk_id: str,
    title: str,
    text: str,
    *,
    intent_key: str | None = "registration.main",
    topic_key: str = "registration",
    published_at: str | None = "2026-07-16",
) -> TextChunk:
    return TextChunk(
        id=chunk_id,
        post_id=f"post-{chunk_id}",
        source="kumoh",
        title=title,
        text=text,
        url=f"https://example.com/{chunk_id}",
        published_at=published_at,
        chunk_index=0,
        topic_key=topic_key,
        topic_label="수강신청",
        is_latest_topic=False,
        intent_key=intent_key,
    )


def make_candidate(
    chunk: TextChunk,
    *,
    dense_score: float = 0.8,
    lexical_score: float = 0.8,
    dense_rank: int | None = 1,
    lexical_rank: int | None = 1,
    fused_score: float = 1.0,
) -> HybridCandidate:
    return HybridCandidate(
        chunk=chunk,
        dense_score=dense_score,
        lexical_score=lexical_score,
        dense_rank=dense_rank,
        lexical_rank=lexical_rank,
        fused_score=fused_score,
    )


def confirmed_intent() -> IntentOption:
    return IntentOption(
        topic_key="registration",
        intent_key="registration.main",
        label="수강신청 일정",
        example="수강신청 기간과 방법",
    )


def query_intent(**updates: object) -> QueryIntent:
    values: dict[str, object] = {
        "topic_key": "registration",
        "requested_year": None,
        "requested_term": None,
        "recency_requested": False,
        "match_terms": ("수강신청", "공지"),
        "distinctive_terms": ("수강신청",),
    }
    values.update(updates)
    return QueryIntent(**values)


def registration_rule() -> IntentRule:
    return IntentRule(
        key="registration.main",
        label="수강신청 일정",
        keywords=("수강신청",),
        evidence_markers=("수강신청", "신청 기간"),
        exclusion_markers=("출석인정",),
        example="수강신청 기간과 방법",
    )


def test_newer_wrong_subintent_ranks_after_older_confirmed_intent() -> None:
    older_main = make_candidate(
        make_chunk("main", "2025 수강신청 일정", "신청 기간과 방법"),
        fused_score=0.2,
    )
    newer_attendance = make_candidate(
        make_chunk(
            "attendance",
            "2026 조기취업자 출석인정 안내",
            "출석인정 신청과 증빙서류",
            intent_key="registration.attendance",
            published_at="2026-07-16",
        ),
        fused_score=1.0,
    )

    results = rerank(
        [newer_attendance, older_main],
        confirmed_intent(),
        query_intent(),
        intent_rule=registration_rule(),
    )

    assert [item.candidate.chunk.id for item in results] == ["main", "attendance"]
    assert results[1].has_intent_conflict is True


def test_explicit_conflicting_year_is_not_temporally_compatible() -> None:
    result = rerank(
        [make_candidate(make_chunk("old", "2025 수강신청 일정", "신청 기간"))],
        confirmed_intent(),
        query_intent(requested_year=2026),
        intent_rule=registration_rule(),
    )[0]

    assert result.temporal_match is False


def test_missing_candidate_temporal_metadata_is_not_a_conflict() -> None:
    result = rerank(
        [make_candidate(make_chunk("unknown", "수강신청 일정", "신청 기간"))],
        confirmed_intent(),
        query_intent(requested_year=2026),
        intent_rule=registration_rule(),
    )[0]

    assert result.temporal_match is True


def test_marker_flags_are_computed_independently_and_normalize_spacing() -> None:
    result = rerank(
        [
            make_candidate(
                make_chunk("markers", "수강 신청 일정", "신청   기간과 방법")
            )
        ],
        confirmed_intent(),
        query_intent(),
        intent_rule=registration_rule(),
    )[0]

    assert result.title_marker_match is True
    assert result.body_marker_match is True


def test_body_exclusion_does_not_override_exact_intent_metadata() -> None:
    result = rerank(
        [
            make_candidate(
                make_chunk("trusted", "수강신청 일정", "출석인정은 별도 안내")
            )
        ],
        confirmed_intent(),
        query_intent(),
        intent_rule=registration_rule(),
    )[0]

    assert result.has_intent_conflict is False


def test_title_exclusion_is_hard_even_with_exact_intent_metadata() -> None:
    result = rerank(
        [
            make_candidate(
                make_chunk("title-exclusion", "출석인정 수강신청", "신청 기간")
            )
        ],
        confirmed_intent(),
        query_intent(),
        intent_rule=registration_rule(),
    )[0]

    assert result.has_intent_conflict is True


def test_topic_or_explicit_intent_mismatch_is_hard_conflict() -> None:
    mismatched_topic = make_candidate(
        make_chunk("topic", "수강신청 일정", "신청 기간", topic_key="career")
    )
    mismatched_intent = make_candidate(
        make_chunk(
            "intent",
            "수강신청 일정",
            "신청 기간",
            intent_key="registration.attendance",
        )
    )

    results = rerank(
        [mismatched_topic, mismatched_intent],
        confirmed_intent(),
        query_intent(),
        intent_rule=registration_rule(),
    )

    assert all(item.has_intent_conflict for item in results)


def test_reranker_validates_intent_topic_against_query_intent() -> None:
    with pytest.raises(ValueError, match="topic"):
        rerank(
            [],
            IntentOption("career", "career.general", "진로", "진로"),
            query_intent(),
        )


def test_reranked_candidate_is_frozen() -> None:
    result = rerank(
        [make_candidate(make_chunk("one", "수강신청", "신청 기간"))],
        confirmed_intent(),
        query_intent(),
        intent_rule=registration_rule(),
    )[0]

    assert isinstance(result, RerankedCandidate)
    with pytest.raises(FrozenInstanceError):
        result.score = 0.0  # type: ignore[misc]


def test_rerank_uses_deterministic_id_ties_without_publication_boost() -> None:
    newer = make_candidate(
        make_chunk("z-new", "수강신청 일정", "신청 기간", published_at="2026-07-16")
    )
    older = make_candidate(
        make_chunk("a-old", "수강신청 일정", "신청 기간", published_at="2025-01-01")
    )

    results = rerank(
        [newer, older],
        confirmed_intent(),
        query_intent(),
        intent_rule=registration_rule(),
    )

    assert [item.candidate.chunk.id for item in results] == ["a-old", "z-new"]


def test_rerank_empty_list() -> None:
    assert rerank([], confirmed_intent(), query_intent()) == []
