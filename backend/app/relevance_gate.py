from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from backend.app.reranker import RerankedCandidate

RelevanceLabel = Literal["relevant", "ambiguous", "irrelevant"]


@dataclass(frozen=True)
class RelevanceDecision:
    candidate: RerankedCandidate
    label: RelevanceLabel
    reason: str


def judge_relevance(candidate: RerankedCandidate) -> RelevanceDecision:
    if candidate.has_intent_conflict:
        return RelevanceDecision(candidate, "irrelevant", "intent_conflict")
    if not candidate.temporal_match:
        return RelevanceDecision(candidate, "irrelevant", "temporal_mismatch")

    signal_count = candidate.candidate.signal_count
    has_exact_evidence = candidate.title_marker_match or candidate.body_marker_match
    if has_exact_evidence and signal_count >= 2:
        return RelevanceDecision(candidate, "relevant", "two_signal_evidence")
    if candidate.title_marker_match and candidate.candidate.lexical_rank is not None:
        return RelevanceDecision(candidate, "relevant", "title_lexical_evidence")
    return RelevanceDecision(candidate, "ambiguous", "insufficient_evidence")


def evaluate_candidates(
    candidates: Sequence[RerankedCandidate],
) -> list[RelevanceDecision]:
    return [judge_relevance(candidate) for candidate in candidates]


def relevant_candidates(
    decisions: Sequence[RelevanceDecision],
) -> list[RerankedCandidate]:
    relevant: list[RerankedCandidate] = []
    for decision in decisions:
        if not isinstance(decision, RelevanceDecision):
            raise TypeError("relevant_candidates expects RelevanceDecision items")
        if decision.label == "relevant":
            relevant.append(decision.candidate)
    return relevant
