from __future__ import annotations

from copy import deepcopy

import pytest
from backend.app.domain import TextChunk
from backend.app.freshness_selector import select_freshest
from backend.app.hybrid_retriever import HybridCandidate
from backend.app.reranker import RerankedCandidate


def make_candidate(
    chunk_id: str,
    *,
    url: str | None = None,
    published_at: str | None = "2026-02-11",
    topic_key: str = "registration",
    intent_key: str | None = "registration.main",
    score: float = 1.0,
    fused_score: float = 0.02,
    dense_rank: int | None = 1,
    lexical_rank: int | None = 1,
    temporal_match: bool = True,
    has_intent_conflict: bool = False,
    chunk_index: int = 0,
) -> RerankedCandidate:
    chunk = TextChunk(
        id=chunk_id,
        post_id=f"post-{chunk_id}",
        source="kumoh",
        title="수강신청 안내",
        text="본문: 수강신청 기간 안내",
        url=url or f"https://example.com/{chunk_id}",
        published_at=published_at,
        chunk_index=chunk_index,
        topic_key=topic_key,
        topic_label="수강신청",
        is_latest_topic=False,
        intent_key=intent_key,
    )
    hybrid = HybridCandidate(
        chunk=chunk,
        dense_score=0.8,
        lexical_score=0.7,
        dense_rank=dense_rank,
        lexical_rank=lexical_rank,
        fused_score=fused_score,
    )
    return RerankedCandidate(
        candidate=hybrid,
        score=score,
        title_marker_match=True,
        body_marker_match=True,
        temporal_match=temporal_match,
        has_intent_conflict=has_intent_conflict,
    )


def test_selects_latest_same_intent_and_does_not_rescue_newer_wrong_intent() -> None:
    old_main = make_candidate("main-old", published_at="2025-08-07")
    newer_wrong_intent = make_candidate(
        "attendance-new",
        published_at="2026-06-16",
        intent_key="registration.attendance",
        has_intent_conflict=True,
    )

    selected = select_freshest([newer_wrong_intent, old_main])

    assert [item.candidate.chunk.id for item in selected] == ["main-old"]


def test_deduplicates_chunks_by_url_using_strongest_candidate_then_selects_newest_url() -> None:
    weaker_chunk = make_candidate(
        "same-url-older-chunk",
        url="https://example.com/main",
        score=0.5,
        fused_score=0.01,
        chunk_index=3,
    )
    stronger_chunk = make_candidate(
        "same-url-stronger-chunk",
        url="https://example.com/main",
        score=0.9,
        fused_score=0.02,
        chunk_index=1,
    )
    newest_url = make_candidate(
        "newest-url",
        url="https://example.com/newest",
        published_at="2026-07-01",
    )

    selected = select_freshest([weaker_chunk, newest_url, stronger_chunk])

    assert [item.candidate.chunk.id for item in selected] == ["newest-url"]


def test_duplicate_url_uses_fused_score_after_reranker_score_tie() -> None:
    lower_fused = make_candidate(
        "lower-fused",
        url="https://example.com/fused",
        score=0.8,
        fused_score=0.01,
        dense_rank=2,
        lexical_rank=2,
    )
    higher_fused = make_candidate(
        "higher-fused",
        url="https://example.com/fused",
        score=0.8,
        fused_score=0.02,
        dense_rank=1,
        lexical_rank=1,
    )

    selected = select_freshest([lower_fused, higher_fused])

    assert [item.candidate.chunk.id for item in selected] == ["higher-fused"]


def test_valid_dates_outrank_missing_and_invalid_dates_and_require_dated_drops_them() -> None:
    valid = make_candidate("valid", url="https://example.com/valid", published_at="2025-01-01")
    missing = make_candidate("missing", url="https://example.com/missing", published_at=None)
    invalid = make_candidate(
        "invalid",
        url="https://example.com/invalid",
        published_at="not-a-date",
    )

    selected = select_freshest([missing, invalid, valid])
    dated_only = select_freshest([missing, invalid, valid], require_dated=True)

    assert [item.candidate.chunk.id for item in selected] == ["valid"]
    assert [item.candidate.chunk.id for item in dated_only] == ["valid"]


def test_all_undated_candidates_are_dropped_when_dated_candidates_are_required() -> None:
    candidates = [
        make_candidate("missing", published_at=None),
        make_candidate("invalid", published_at="not-a-date"),
    ]

    assert select_freshest(candidates, require_dated=True) == []


def test_timezone_tie_is_compared_as_an_instant_then_score_resolves() -> None:
    same_instant_low_score = make_candidate(
        "a-tie",
        url="https://example.com/a",
        published_at="2025-12-31T16:00:00Z",
        score=0.4,
    )
    same_instant_high_score = make_candidate(
        "b-tie",
        url="https://example.com/b",
        published_at="2026-01-01T01:00:00+09:00",
        score=0.8,
    )

    selected = select_freshest([same_instant_low_score, same_instant_high_score])

    assert [item.candidate.chunk.id for item in selected] == ["b-tie"]


def test_duplicate_url_uses_chunk_index_then_id_after_quality_ties() -> None:
    higher_chunk_index = make_candidate(
        "a-id",
        url="https://example.com/tie",
        chunk_index=2,
    )
    lower_chunk_index = make_candidate(
        "z-id",
        url="https://example.com/tie",
        chunk_index=1,
    )

    selected = select_freshest([higher_chunk_index, lower_chunk_index])

    assert [item.candidate.chunk.id for item in selected] == ["z-id"]


def test_same_url_conflicting_topic_intent_or_canonical_date_raises() -> None:
    same_url = make_candidate("one", url="https://example.com/conflict")
    conflicting_intent = make_candidate(
        "two",
        url="https://example.com/conflict",
        intent_key="registration.attendance",
    )

    with pytest.raises(ValueError, match="conflicting metadata"):
        select_freshest([same_url, conflicting_intent])

    conflicting_topic = make_candidate(
        "topic-conflict",
        url="https://example.com/topic-conflict",
        topic_key="graduation",
    )
    same_topic_url = make_candidate(
        "topic-conflict-2",
        url="https://example.com/topic-conflict",
    )

    with pytest.raises(ValueError, match="conflicting metadata"):
        select_freshest([conflicting_topic, same_topic_url])

    canonical_date_one = make_candidate(
        "canonical-one",
        url="https://example.com/canonical-date",
        published_at="2025-12-31T16:00:00Z",
    )
    canonical_date_same_instant = make_candidate(
        "canonical-two",
        url="https://example.com/canonical-date",
        published_at="2026-01-01T01:00:00+09:00",
    )

    assert select_freshest([canonical_date_one, canonical_date_same_instant]) == [
        canonical_date_one
    ]

    conflicting_date = make_candidate(
        "three",
        url="https://example.com/date-conflict",
        published_at="2026-02-11",
    )
    other_date = make_candidate(
        "four",
        url="https://example.com/date-conflict",
        published_at="2026-02-12",
    )

    with pytest.raises(ValueError, match="conflicting metadata"):
        select_freshest([conflicting_date, other_date])


def test_conflicting_url_metadata_raises_before_conflict_filtering() -> None:
    accepted = make_candidate("accepted", url="https://example.com/dropped")
    dropped = make_candidate(
        "dropped",
        url="https://example.com/dropped",
        intent_key="registration.attendance",
        has_intent_conflict=True,
    )

    with pytest.raises(ValueError, match="conflicting metadata"):
        select_freshest([accepted, dropped])


def test_all_conflicting_candidates_produce_no_evidence() -> None:
    candidates = [
        make_candidate("intent", has_intent_conflict=True),
        make_candidate("temporal", temporal_match=False),
    ]

    assert select_freshest(candidates) == []


def test_candidates_and_require_dated_are_validated() -> None:
    candidate = make_candidate("valid")

    with pytest.raises(TypeError, match="Sequence"):
        select_freshest(iter([candidate]))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RerankedCandidate"):
        select_freshest([object()])  # type: ignore[list-item]
    with pytest.raises(TypeError, match="require_dated"):
        select_freshest([candidate], require_dated=1)  # type: ignore[arg-type]


def test_legacy_none_intent_groups_by_topic_and_input_is_not_mutated() -> None:
    candidates = [
        make_candidate(
            "career-old",
            topic_key="career",
            intent_key=None,
            published_at="2025-01-01",
        ),
        make_candidate(
            "career-new",
            topic_key="career",
            intent_key=None,
            published_at="2026-01-01",
        ),
        make_candidate(
            "general-new",
            topic_key="general",
            intent_key=None,
            published_at="2026-02-01",
        ),
    ]
    snapshot = deepcopy(candidates)

    selected = select_freshest(candidates)

    assert [item.candidate.chunk.id for item in selected] == ["general-new", "career-new"]
    assert candidates == snapshot
