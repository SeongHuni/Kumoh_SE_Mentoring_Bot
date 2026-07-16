from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from backend.app.domain import TextChunk
from backend.app.hybrid_retriever import HybridCandidate
from backend.app.intent_analysis import IntentOption
from backend.app.query_intent import TERM_PATTERNS, QueryIntent, compact
from backend.app.topic_rules import IntentRule

YEAR_PATTERN = re.compile(r"(?<!\d)((?:19|20)\d{2})(?:학년도|년)?(?!\d)")
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
GENERIC_MARKERS = frozenset(
    {
        "공지",
        "공식",
        "관련",
        "기간",
        "방법",
        "안내",
        "알려줘",
        "일반",
        "일정",
        "정보",
        "신청",
        "확인",
        "학기",
        "학년도",
    }
)


@dataclass(frozen=True)
class RerankedCandidate:
    candidate: HybridCandidate
    score: float
    title_marker_match: bool
    body_marker_match: bool
    temporal_match: bool
    has_intent_conflict: bool


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_marker(text: str, marker: str) -> bool:
    normalized_marker = compact(marker)
    return bool(normalized_marker) and normalized_marker in compact(text)


def _fallback_markers(intent: IntentOption, query_intent: QueryIntent) -> tuple[str, ...]:
    values = (
        intent.label,
        intent.example,
        *query_intent.distinctive_terms,
        *query_intent.match_terms,
    )
    markers: set[str] = set()
    for value in values:
        normalized_value = _normalized(value)
        compact_value = compact(value)
        tokens = tuple(TOKEN_PATTERN.findall(value.casefold()))
        useful_tokens = tuple(
            token
            for token in tokens
            if len(compact(token)) >= 2 and compact(token) not in GENERIC_MARKERS
        )
        if compact_value and useful_tokens:
            markers.add(normalized_value)
        markers.update(compact(token) for token in useful_tokens)
    return tuple(sorted(markers, key=lambda marker: (-len(compact(marker)), marker)))


def _markers(
    intent: IntentOption,
    query_intent: QueryIntent,
    rule: IntentRule | None,
) -> tuple[str, ...]:
    if rule is not None:
        return tuple(dict.fromkeys((*rule.keywords, *rule.evidence_markers)))
    return _fallback_markers(intent, query_intent)


def _candidate_years(chunk: TextChunk) -> set[int]:
    text = f"{chunk.title}\n{chunk.text}"
    return {int(match.group(1)) for match in YEAR_PATTERN.finditer(text)}


def _candidate_terms(chunk: TextChunk) -> set[str]:
    text = f"{chunk.title}\n{chunk.text}"
    return {
        term
        for term, pattern in TERM_PATTERNS
        if pattern.search(text)
    }


def _temporal_match(chunk: TextChunk, query_intent: QueryIntent) -> bool:
    years = _candidate_years(chunk)
    if query_intent.requested_year is not None and years:
        if query_intent.requested_year not in years:
            return False

    terms = _candidate_terms(chunk)
    if query_intent.requested_term is not None and terms:
        if query_intent.requested_term not in terms:
            return False
    return True


def _has_intent_conflict(
    chunk: TextChunk,
    intent: IntentOption,
    intent_rule: IntentRule | None,
) -> bool:
    if chunk.topic_key != intent.topic_key:
        return True
    explicit_intent_key = (chunk.intent_key or "").strip()
    if explicit_intent_key and explicit_intent_key != intent.intent_key:
        return True
    if intent_rule is None:
        return False

    title_exclusion = any(
        _contains_marker(chunk.title, marker)
        for marker in intent_rule.exclusion_markers
    )
    if title_exclusion:
        return True

    exact_intent_metadata = explicit_intent_key == intent.intent_key
    body_exclusion = any(
        _contains_marker(chunk.text, marker)
        for marker in intent_rule.exclusion_markers
    )
    return body_exclusion and not exact_intent_metadata


def _score(
    candidate: HybridCandidate,
    *,
    title_marker_match: bool,
    body_marker_match: bool,
) -> float:
    signal_score = (
        candidate.fused_score
        + (candidate.dense_score * 0.01)
        + (candidate.lexical_score * 0.01)
        + (candidate.signal_count * 0.05)
    )
    marker_score = (0.30 if title_marker_match else 0.0) + (
        0.15 if body_marker_match else 0.0
    )
    return signal_score + marker_score


def rerank(
    candidates: Sequence[HybridCandidate],
    intent: IntentOption,
    query_intent: QueryIntent,
    *,
    intent_rule: IntentRule | None = None,
) -> list[RerankedCandidate]:
    if intent.topic_key != query_intent.topic_key:
        raise ValueError("intent and query_intent topic must match")

    markers = _markers(intent, query_intent, intent_rule)
    reranked: list[RerankedCandidate] = []
    for candidate in candidates:
        title_marker_match = any(
            _contains_marker(candidate.chunk.title, marker) for marker in markers
        )
        body_marker_match = any(
            _contains_marker(candidate.chunk.text, marker) for marker in markers
        )
        temporal_match = _temporal_match(candidate.chunk, query_intent)
        has_intent_conflict = _has_intent_conflict(
            candidate.chunk,
            intent,
            intent_rule,
        )
        reranked.append(
            RerankedCandidate(
                candidate=candidate,
                score=_score(
                    candidate,
                    title_marker_match=title_marker_match,
                    body_marker_match=body_marker_match,
                ),
                title_marker_match=title_marker_match,
                body_marker_match=body_marker_match,
                temporal_match=temporal_match,
                has_intent_conflict=has_intent_conflict,
            )
        )

    return sorted(
        reranked,
        key=lambda item: (
            item.has_intent_conflict or not item.temporal_match,
            -item.score,
            item.candidate.chunk.id,
        ),
    )
