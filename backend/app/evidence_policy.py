from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain import RetrievedChunk
from backend.app.query_intent import QueryIntent, compact, extract_term, extract_year
from backend.app.topic_rules import TopicCatalog, TopicRule


@dataclass(frozen=True)
class EvidenceDecision:
    accepted: bool
    reason: str


def _matches_marker(intent: QueryIntent, marker: str, title: str) -> bool:
    normalized_marker = compact(marker)
    normalized_title = compact(title)
    if not normalized_marker or normalized_marker not in normalized_title:
        return False
    return any(
        normalized_marker in term or term in normalized_marker
        for term in intent.match_terms
        if len(term) >= 2
    )


def decide_evidence(
    intent: QueryIntent,
    *,
    topic: TopicRule,
    catalog: TopicCatalog,
    item: RetrievedChunk,
) -> EvidenceDecision:
    title = item.chunk.title
    title_year = extract_year(title)
    title_term = extract_term(title)
    if intent.requested_year is not None:
        if title_year is None:
            return EvidenceDecision(False, "missing_temporal_evidence")
        if title_year != intent.requested_year:
            return EvidenceDecision(False, "year_mismatch")
    if intent.requested_term is not None:
        if title_term is None:
            return EvidenceDecision(False, "missing_temporal_evidence")
        if title_term != intent.requested_term:
            return EvidenceDecision(False, "semester_mismatch")

    if intent.topic_key == catalog.default_topic_key and intent.recency_requested:
        return EvidenceDecision(True, "accepted_general_latest")

    if any(_matches_marker(intent, marker, title) for marker in topic.evidence_markers):
        return EvidenceDecision(True, "accepted_topic_marker")

    normalized_title = compact(title)
    overlaps = {
        term
        for term in intent.distinctive_terms
        if len(term) >= 2 and compact(term) in normalized_title
    }
    if len(overlaps) >= 2 or any(len(compact(term)) >= 5 for term in overlaps):
        return EvidenceDecision(True, "accepted_title_overlap")
    return EvidenceDecision(False, "insufficient_title_evidence")
