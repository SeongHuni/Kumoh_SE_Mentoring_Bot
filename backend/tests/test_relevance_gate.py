import pytest
from backend.app.domain import TextChunk
from backend.app.hybrid_retriever import HybridCandidate
from backend.app.relevance_gate import (
    RelevanceDecision,
    evaluate_candidates,
    judge_relevance,
    relevant_candidates,
)
from backend.app.reranker import RerankedCandidate


def make_chunk(
    chunk_id: str,
    title: str,
    text: str,
    *,
    intent_key: str | None = "registration.main",
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
        is_latest_topic=False,
        intent_key=intent_key,
    )


def make_reranked(
    chunk: TextChunk,
    *,
    title_marker_match: bool = False,
    body_marker_match: bool = False,
    temporal_match: bool = True,
    has_intent_conflict: bool = False,
    signal_count: int = 2,
) -> RerankedCandidate:
    candidate = HybridCandidate(
        chunk=chunk,
        dense_score=0.8 if signal_count == 2 else 0.0,
        lexical_score=0.8 if signal_count >= 1 else 0.0,
        dense_rank=1 if signal_count == 2 else None,
        lexical_rank=1 if signal_count >= 1 else None,
        fused_score=1.0,
    )
    return RerankedCandidate(
        candidate=candidate,
        score=1.0,
        title_marker_match=title_marker_match,
        body_marker_match=body_marker_match,
        temporal_match=temporal_match,
        has_intent_conflict=has_intent_conflict,
    )


def test_two_signal_consensus_with_exact_body_evidence_is_relevant() -> None:
    candidate = make_reranked(
        make_chunk("both", "학사 안내", "수강신청 기간과 방법"),
        body_marker_match=True,
    )

    decision = judge_relevance(candidate)

    assert decision == RelevanceDecision(candidate, "relevant", "two_signal_evidence")


def test_exact_title_marker_with_lexical_signal_is_relevant() -> None:
    candidate = make_reranked(
        make_chunk("title", "수강신청 일정", "신청 기간"),
        title_marker_match=True,
        signal_count=1,
    )

    assert judge_relevance(candidate).label == "relevant"


def test_dense_only_evidence_is_ambiguous() -> None:
    candidate = make_reranked(
        make_chunk("dense", "학사 안내", "신청 기간"),
        body_marker_match=True,
        signal_count=2,
    )
    candidate = RerankedCandidate(
        candidate=candidate.candidate.__class__(
            chunk=candidate.candidate.chunk,
            dense_score=0.8,
            lexical_score=0.0,
            dense_rank=1,
            lexical_rank=None,
            fused_score=1.0,
        ),
        score=candidate.score,
        title_marker_match=candidate.title_marker_match,
        body_marker_match=candidate.body_marker_match,
        temporal_match=candidate.temporal_match,
        has_intent_conflict=candidate.has_intent_conflict,
    )

    assert judge_relevance(candidate).label == "ambiguous"


def test_conflict_is_irrelevant_even_with_strong_evidence() -> None:
    candidate = make_reranked(
        make_chunk("conflict", "수강신청 일정", "수강신청 기간"),
        title_marker_match=True,
        body_marker_match=True,
        has_intent_conflict=True,
    )

    assert judge_relevance(candidate).label == "irrelevant"


def test_temporal_mismatch_is_irrelevant() -> None:
    candidate = make_reranked(
        make_chunk("time", "수강신청 일정", "수강신청 기간"),
        title_marker_match=True,
        temporal_match=False,
    )

    assert judge_relevance(candidate).label == "irrelevant"


def test_evaluate_preserves_order_and_relevant_candidates_fail_closed() -> None:
    ambiguous = make_reranked(make_chunk("ambiguous", "학사 안내", "신청"))
    relevant = make_reranked(
        make_chunk("relevant", "수강신청 일정", "신청"),
        title_marker_match=True,
        signal_count=1,
    )
    irrelevant = make_reranked(
        make_chunk("irrelevant", "수강신청 일정", "신청"),
        title_marker_match=True,
        has_intent_conflict=True,
    )

    decisions = evaluate_candidates([ambiguous, relevant, irrelevant])

    assert [decision.candidate.candidate.chunk.id for decision in decisions] == [
        "ambiguous",
        "relevant",
        "irrelevant",
    ]
    assert [item.candidate.chunk.id for item in relevant_candidates(decisions)] == [
        "relevant"
    ]


def test_relevant_candidates_rejects_raw_reranked_candidates() -> None:
    candidate = make_reranked(
        make_chunk("raw", "수강신청 일정", "신청"),
        title_marker_match=True,
        signal_count=1,
    )

    with pytest.raises(TypeError, match="RelevanceDecision"):
        relevant_candidates([candidate])  # type: ignore[list-item]


def test_relevance_gate_empty_list() -> None:
    assert evaluate_candidates([]) == []
    assert relevant_candidates([]) == []
