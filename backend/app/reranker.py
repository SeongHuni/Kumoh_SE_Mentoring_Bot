from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real

from backend.app.domain import TextChunk
from backend.app.hybrid_retriever import HybridCandidate
from backend.app.intent_analysis import IntentOption
from backend.app.query_intent import TERM_PATTERNS, QueryIntent
from backend.app.topic_rules import IntentRule

YEAR_PATTERN = re.compile(r"(?<!\d)((?:19|20)\d{2})(?:학년도|년)?(?!\d)")
TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
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
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(TOKEN_PATTERN.findall(unicodedata.normalize("NFKC", value).casefold()))


def _compact(value: str) -> str:
    return "".join(_tokens(value))


def _contains_marker(text: str, marker: str) -> bool:
    marker_tokens = _tokens(marker)
    if not marker_tokens:
        return False

    normalized_marker = "".join(marker_tokens)
    text_tokens = _tokens(text)
    if any(token.startswith(normalized_marker) for token in text_tokens):
        return True

    for start in range(len(text_tokens)):
        combined = ""
        for token in text_tokens[start:]:
            combined += token
            if combined == normalized_marker:
                return True
            if len(combined) >= len(normalized_marker):
                break

        if len(marker_tokens) > 1:
            matches = True
            for offset, marker_token in enumerate(marker_tokens):
                text_index = start + offset
                if text_index >= len(text_tokens):
                    matches = False
                    break
                text_token = text_tokens[text_index]
                if offset < len(marker_tokens) - 1:
                    if text_token != marker_token:
                        matches = False
                        break
                elif not text_token.startswith(marker_token):
                    matches = False
                    break
            if matches:
                return True
    return False


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
        compact_value = _compact(value)
        tokens = _tokens(value)
        useful_tokens = tuple(
            token
            for token in tokens
            if len(token) >= 2 and token not in GENERIC_MARKERS
        )
        if compact_value and useful_tokens:
            markers.add(normalized_value)
        markers.update(useful_tokens)
    return tuple(sorted(markers, key=lambda marker: (-len(_compact(marker)), marker)))


def _markers(
    intent: IntentOption,
    query_intent: QueryIntent,
    rule: IntentRule | None,
) -> tuple[str, ...]:
    if rule is not None:
        return tuple(dict.fromkeys((*rule.keywords, *rule.evidence_markers)))
    return _fallback_markers(intent, query_intent)


def _candidate_years(text: str) -> set[int]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return {int(match.group(1)) for match in YEAR_PATTERN.finditer(normalized)}


def _candidate_terms(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return {
        term
        for term, pattern in TERM_PATTERNS
        if pattern.search(normalized)
    }


def _actual_body(chunk: TextChunk) -> str:
    normalized_text = _normalized(chunk.text)
    delimiter = "본문:"
    if delimiter in normalized_text:
        return normalized_text.split(delimiter, 1)[1].strip()

    normalized_title = _normalized(chunk.title)
    if not normalized_title:
        return normalized_text
    title_pattern = re.compile(
        rf"(?<![^\W_]){re.escape(normalized_title)}(?![^\W_])",
        re.UNICODE,
    )
    return title_pattern.sub("", normalized_text, count=1).strip()


def _temporal_match(chunk: TextChunk, query_intent: QueryIntent) -> bool:
    body = _actual_body(chunk)
    if query_intent.requested_year is not None:
        title_years = _candidate_years(chunk.title)
        years = title_years or _candidate_years(body)
        if years and years != {query_intent.requested_year}:
            return False

    if query_intent.requested_term is not None:
        title_terms = _candidate_terms(chunk.title)
        terms = title_terms or _candidate_terms(body)
        if terms and terms != {query_intent.requested_term}:
            return False
    return True


def _has_intent_conflict(
    chunk: TextChunk,
    intent: IntentOption,
    intent_rule: IntentRule | None,
    body: str,
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
        _contains_marker(body, marker)
        for marker in intent_rule.exclusion_markers
    )
    return body_exclusion and not exact_intent_metadata


def _validate_finite_score(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{name} must be a finite nonnegative real number")


def _validate_rank(value: object, name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _validate_candidate(candidate: HybridCandidate) -> None:
    _validate_finite_score(candidate.fused_score, "fused_score")
    _validate_finite_score(candidate.dense_score, "dense_score")
    _validate_finite_score(candidate.lexical_score, "lexical_score")
    _validate_rank(candidate.dense_rank, "dense_rank")
    _validate_rank(candidate.lexical_rank, "lexical_rank")


def _score(
    candidate: HybridCandidate,
    *,
    title_marker_match: bool,
    body_marker_match: bool,
) -> float:
    signal_score = (
        candidate.fused_score
        + (min(candidate.signal_count, 2) * 0.05)
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
    if intent_rule is not None and intent_rule.key != intent.intent_key:
        raise ValueError("intent_rule key must match intent key")

    markers = _markers(intent, query_intent, intent_rule)
    reranked: list[RerankedCandidate] = []
    for candidate in candidates:
        _validate_candidate(candidate)
        body = _actual_body(candidate.chunk)
        title_marker_match = any(
            _contains_marker(candidate.chunk.title, marker) for marker in markers
        )
        body_marker_match = any(
            _contains_marker(body, marker) for marker in markers
        )
        temporal_match = _temporal_match(candidate.chunk, query_intent)
        has_intent_conflict = _has_intent_conflict(
            candidate.chunk,
            intent,
            intent_rule,
            body,
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
