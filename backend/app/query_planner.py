from __future__ import annotations

from dataclasses import dataclass

from backend.app.intent_analysis import IntentOption
from backend.app.query_intent import QueryIntent

TERM_LABELS = {
    "first": "1학기",
    "second": "2학기",
    "summer": "여름 계절학기",
    "winter": "겨울 계절학기",
}


@dataclass(frozen=True)
class QueryPlan:
    original: str
    queries: tuple[str, ...]
    hypothetical_notice: str


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _temporal_text(query_intent: QueryIntent) -> str:
    parts: list[str] = []
    if query_intent.requested_year is not None:
        parts.append(f"{query_intent.requested_year}학년도")
    if query_intent.requested_term is not None:
        parts.append(TERM_LABELS[query_intent.requested_term])
    return " ".join(parts)


def _deduplicate(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def build_query_plan(
    question: str,
    intent: IntentOption,
    query_intent: QueryIntent,
) -> QueryPlan:
    original = _normalize(question)
    if not original:
        raise ValueError("question must not be blank")
    if intent.topic_key != query_intent.topic_key:
        raise ValueError("intent and query_intent topic must match")

    temporal = _temporal_text(query_intent)
    rewrite = " ".join(
        part
        for part in (temporal, _normalize(intent.label), "공식 공지")
        if part
    )
    example = _normalize(intent.example)
    hypothetical_notice = (
        f"제목: {rewrite}\n"
        f"본문: {temporal + ' ' if temporal else ''}{example} 관련 공식 공지의 일정, "
        "신청 방법과 유의사항을 안내합니다."
    )
    return QueryPlan(
        original=original,
        queries=_deduplicate((original, rewrite, hypothetical_notice)),
        hypothetical_notice=hypothetical_notice,
    )
