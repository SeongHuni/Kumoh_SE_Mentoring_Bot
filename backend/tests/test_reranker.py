import math
from dataclasses import FrozenInstanceError, replace

import pytest
from backend.app.domain import TextChunk
from backend.app.hybrid_retriever import HybridCandidate, reciprocal_rank
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
    fused_score: float | None = None,
) -> HybridCandidate:
    valid_fused_score = (
        reciprocal_rank(dense_rank) + reciprocal_rank(lexical_rank)
        if fused_score is None
        else fused_score
    )
    return HybridCandidate(
        chunk=chunk,
        dense_score=dense_score,
        lexical_score=lexical_score,
        dense_rank=dense_rank,
        lexical_rank=lexical_rank,
        fused_score=valid_fused_score,
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
        make_chunk("main", "2025 수강신청 일정", "신청 기간과 방법")
    )
    newer_attendance = make_candidate(
        make_chunk(
            "attendance",
            "2026 조기취업자 출석인정 안내",
            "출석인정 신청과 증빙서류",
            intent_key="registration.attendance",
            published_at="2026-07-16",
        ),
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


def test_title_year_takes_precedence_over_conflicting_body_year() -> None:
    result = rerank(
        [
            make_candidate(
                make_chunk(
                    "title-year",
                    "2025 수강신청 일정",
                    "본문: 2026학년도에도 적용되는 안내",
                )
            )
        ],
        confirmed_intent(),
        query_intent(requested_year=2026),
        intent_rule=registration_rule(),
    )[0]

    assert result.temporal_match is False


def test_multiple_title_years_fail_closed_even_when_requested_year_is_present() -> None:
    result = rerank(
        [
            make_candidate(
                make_chunk("multi-title-year", "2025·2026 수강신청 일정", "신청 기간")
            )
        ],
        confirmed_intent(),
        query_intent(requested_year=2026),
        intent_rule=registration_rule(),
    )[0]

    assert result.temporal_match is False


def test_body_year_is_used_when_title_has_no_year() -> None:
    result = rerank(
        [
            make_candidate(
                make_chunk("body-year", "수강신청 일정", "본문: 2026학년도 신청 기간")
            )
        ],
        confirmed_intent(),
        query_intent(requested_year=2026),
        intent_rule=registration_rule(),
    )[0]

    assert result.temporal_match is True


def test_multiple_body_years_fail_closed() -> None:
    result = rerank(
        [
            make_candidate(
                make_chunk("multi-body-year", "수강신청 일정", "본문: 2025년과 2026년")
            )
        ],
        confirmed_intent(),
        query_intent(requested_year=2026),
        intent_rule=registration_rule(),
    )[0]

    assert result.temporal_match is False


def test_title_term_takes_precedence_over_conflicting_body_term() -> None:
    result = rerank(
        [
            make_candidate(
                make_chunk(
                    "title-term",
                    "1학기 수강신청 일정",
                    "본문: 2학기 신청 기간",
                )
            )
        ],
        confirmed_intent(),
        query_intent(requested_term="second"),
        intent_rule=registration_rule(),
    )[0]

    assert result.temporal_match is False


def test_multiple_body_terms_fail_closed() -> None:
    result = rerank(
        [
            make_candidate(
                make_chunk("multi-body-term", "수강신청 일정", "본문: 1학기와 2학기")
            )
        ],
        confirmed_intent(),
        query_intent(requested_term="second"),
        intent_rule=registration_rule(),
    )[0]

    assert result.temporal_match is False


def test_missing_candidate_temporal_metadata_for_term_is_compatible() -> None:
    result = rerank(
        [make_candidate(make_chunk("unknown-term", "수강신청 일정", "신청 기간"))],
        confirmed_intent(),
        query_intent(requested_term="second"),
        intent_rule=registration_rule(),
    )[0]

    assert result.temporal_match is True


def test_missing_candidate_temporal_metadata_is_not_a_conflict() -> None:
    result = rerank(
        [make_candidate(make_chunk("unknown", "수강신청 일정", "신청 기간"))],
        confirmed_intent(),
        query_intent(requested_year=2026),
        intent_rule=registration_rule(),
    )[0]

    assert result.temporal_match is True


def test_reranker_rejects_intent_rule_for_a_different_intent() -> None:
    mismatched_rule = IntentRule(
        key="registration.attendance",
        label="출석인정",
        keywords=("출석인정",),
        evidence_markers=(),
        exclusion_markers=(),
        example="출석인정",
    )

    with pytest.raises(ValueError, match="intent_rule"):
        rerank(
            [],
            confirmed_intent(),
            query_intent(),
            intent_rule=mismatched_rule,
        )


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


def test_marker_matching_uses_nfkc_casefold_and_prefixes() -> None:
    rule = IntentRule(
        key="registration.main",
        label="채용",
        keywords=("채용",),
        evidence_markers=("ＡＢＣ",),
        exclusion_markers=(),
        example="채용",
    )
    result = rerank(
        [make_candidate(make_chunk("unicode", "ａｂｃ 채용공고", "본문"))],
        confirmed_intent(),
        query_intent(),
        intent_rule=rule,
    )[0]

    assert result.title_marker_match is True


def test_marker_matching_rejects_unrelated_token_substrings() -> None:
    rule = IntentRule(
        key="registration.main",
        label="채용",
        keywords=("채용",),
        evidence_markers=(),
        exclusion_markers=(),
        example="채용",
    )
    result = rerank(
        [make_candidate(make_chunk("substring", "미채용 안내", "본문"))],
        confirmed_intent(),
        query_intent(),
        intent_rule=rule,
    )[0]

    assert result.title_marker_match is False


def test_marker_matching_accepts_bounded_adjacent_token_concatenation() -> None:
    result = rerank(
        [make_candidate(make_chunk("adjacent", "수강 신청 안내", "본문"))],
        confirmed_intent(),
        query_intent(),
        intent_rule=registration_rule(),
    )[0]

    assert result.title_marker_match is True


def test_body_marker_ignores_title_header_and_does_not_copy_title_match() -> None:
    result = rerank(
        [
            make_candidate(
                make_chunk(
                    "body-header",
                    "수강신청 일정",
                    "제목: 수강신청 일정\n본문: 일반 학사 공지",
                )
            )
        ],
        confirmed_intent(),
        query_intent(),
        intent_rule=registration_rule(),
    )[0]

    assert result.title_marker_match is True
    assert result.body_marker_match is False


def test_body_marker_removes_one_duplicated_title_without_delimiter() -> None:
    result = rerank(
        [
            make_candidate(
                make_chunk("body-duplicate", "수강신청 일정", "수강신청 일정 일반 학사 공지")
            )
        ],
        confirmed_intent(),
        query_intent(),
        intent_rule=registration_rule(),
    )[0]

    assert result.title_marker_match is True
    assert result.body_marker_match is False


def test_body_exclusion_uses_actual_body_after_delimiter() -> None:
    rule = IntentRule(
        key="registration.main",
        label="수강신청",
        keywords=("수강신청",),
        evidence_markers=(),
        exclusion_markers=("출석인정",),
        example="수강신청",
    )
    result = rerank(
        [
            make_candidate(
                make_chunk(
                    "body-exclusion",
                    "수강신청 일정",
                    "출석인정 제목 장식\n본문: 일반 신청 안내",
                    intent_key=None,
                )
            )
        ],
        confirmed_intent(),
        query_intent(),
        intent_rule=rule,
    )[0]

    assert result.has_intent_conflict is False


def test_reranker_score_ignores_incompatible_raw_retrieval_scales() -> None:
    low = make_candidate(
        make_chunk("low", "수강신청 일정", "신청 기간"),
        dense_score=0.1,
        lexical_score=0.5,
    )
    high = make_candidate(
        make_chunk("high", "수강신청 일정", "신청 기간"),
        dense_score=0.9,
        lexical_score=50.0,
    )

    results = rerank(
        [low, high],
        confirmed_intent(),
        query_intent(),
        intent_rule=registration_rule(),
    )

    assert results[0].score == results[1].score


@pytest.mark.parametrize(
    ("dense_rank", "lexical_rank"),
    [(1, 1), (None, 1), (None, None)],
)
def test_valid_fused_score_provenance_for_signal_shapes(
    dense_rank: int | None,
    lexical_rank: int | None,
) -> None:
    candidate = make_candidate(
        make_chunk(f"valid-{dense_rank}-{lexical_rank}", "무관한 제목", "무관한 본문"),
        dense_rank=dense_rank,
        lexical_rank=lexical_rank,
    )
    expected_rrf = reciprocal_rank(dense_rank) + reciprocal_rank(lexical_rank)

    result = rerank([candidate], confirmed_intent(), query_intent())[0]

    assert result.score == expected_rrf + (candidate.signal_count * 0.05)


def test_rerank_recomputes_rrf_with_requested_k() -> None:
    candidate = make_candidate(
        make_chunk("custom-k", "무관한 제목", "무관한 본문"),
        fused_score=reciprocal_rank(1, k=10) * 2,
    )

    result = rerank(
        [candidate],
        confirmed_intent(),
        query_intent(),
        rrf_k=10,
    )[0]

    assert result.score == (reciprocal_rank(1, k=10) * 2) + 0.1


def test_reranker_rejects_huge_forged_fused_score() -> None:
    candidate = make_candidate(
        make_chunk("forged", "무관한 제목", "무관한 본문"),
        fused_score=1e9,
    )

    with pytest.raises(ValueError, match="fused_score"):
        rerank([candidate], confirmed_intent(), query_intent())


def test_reranker_rejects_subtle_fused_score_mismatch() -> None:
    expected_rrf = reciprocal_rank(1) * 2
    candidate = make_candidate(
        make_chunk("subtle", "무관한 제목", "무관한 본문"),
        fused_score=expected_rrf + 1e-6,
    )

    with pytest.raises(ValueError, match="fused_score"):
        rerank([candidate], confirmed_intent(), query_intent())


@pytest.mark.parametrize("rrf_k", [0, -1, True, 1.0])
def test_reranker_rejects_invalid_rrf_k(rrf_k: object) -> None:
    with pytest.raises(ValueError, match="rrf_k"):
        rerank([], confirmed_intent(), query_intent(), rrf_k=rrf_k)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["fused_score", "dense_score", "lexical_score"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_reranker_rejects_nonfinite_scores(field: str, value: float) -> None:
    candidate = make_candidate(make_chunk("nonfinite", "수강신청", "본문"))
    invalid = replace(candidate, **{field: value})

    with pytest.raises(ValueError, match="finite"):
        rerank([invalid], confirmed_intent(), query_intent())


@pytest.mark.parametrize("field", ["dense_rank", "lexical_rank"])
def test_reranker_rejects_invalid_ranks(field: str) -> None:
    candidate = make_candidate(make_chunk("rank", "수강신청", "본문"))
    invalid = replace(candidate, **{field: 0})

    with pytest.raises(ValueError, match="rank"):
        rerank([invalid], confirmed_intent(), query_intent())


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
