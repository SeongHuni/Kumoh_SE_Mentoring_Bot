from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from backend.app.topic_rules import TopicCatalog, TopicRule

AcademicTerm = Literal["first", "second", "summer", "winter"]
TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
YEAR_PATTERN = re.compile(r"(?<!\d)((?:19|20)\d{2})(?:학년도|년)?(?!\d)")
TERM_PATTERNS: tuple[tuple[AcademicTerm, re.Pattern[str]], ...] = (
    ("summer", re.compile(r"여름\s*계절(?:학기|수업)?")),
    ("winter", re.compile(r"겨울\s*계절(?:학기|수업)?")),
    ("first", re.compile(r"1\s*학기")),
    ("second", re.compile(r"2\s*학기")),
)
PARTICLES = (
    "으로",
    "에서",
    "까지",
    "부터",
    "에게",
    "한테",
    "처럼",
    "보다",
    "로",
    "을",
    "를",
    "은",
    "는",
    "이",
    "가",
    "의",
    "와",
    "과",
    "도",
    "에",
)


@dataclass(frozen=True)
class QueryIntent:
    topic_key: str
    requested_year: int | None
    requested_term: AcademicTerm | None
    recency_requested: bool
    match_terms: tuple[str, ...]
    distinctive_terms: tuple[str, ...]


def compact(value: str) -> str:
    return "".join(TOKEN_PATTERN.findall(value.casefold()))


def extract_year(value: str) -> int | None:
    match = YEAR_PATTERN.search(value)
    return int(match.group(1)) if match else None


def extract_term(value: str) -> AcademicTerm | None:
    for term, pattern in TERM_PATTERNS:
        if pattern.search(value):
            return term
    return None


def _strip_particle(token: str) -> str:
    for particle in PARTICLES:
        if len(token) > len(particle) + 1 and token.endswith(particle):
            return token[: -len(particle)]
    return token


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        normalized
        for token in TOKEN_PATTERN.findall(value.casefold())
        if len(normalized := _strip_particle(token)) >= 2
    )


def _phrase_tokens(values: tuple[str, ...]) -> set[str]:
    result: set[str] = set()
    for value in values:
        result.update(_tokens(value))
        normalized = compact(value)
        if normalized:
            result.add(normalized)
    return result


def analyze_query(
    question: str,
    *,
    topic: TopicRule,
    catalog: TopicCatalog,
) -> QueryIntent:
    policy = catalog.retrieval_policy
    normalized_question = compact(question)
    raw_tokens = set(_tokens(question))
    match_terms = set(raw_tokens)
    match_terms.add(normalized_question)
    for group in policy.alias_groups:
        if any(compact(value) in normalized_question for value in group):
            match_terms.update(compact(value) for value in group)

    ignored = _phrase_tokens(topic.keywords + policy.recency_terms + policy.generic_terms)
    year = extract_year(question)
    term = extract_term(question)
    distinctive = {
        token
        for token in raw_tokens
        if token not in ignored
        and not token.isdigit()
        and token not in {"학년도", "학기", "여름계절", "겨울계절"}
    }
    return QueryIntent(
        topic_key=topic.key,
        requested_year=year,
        requested_term=term,
        recency_requested=any(
            compact(value) in normalized_question for value in policy.recency_terms
        ),
        match_terms=tuple(sorted(match_terms)),
        distinctive_terms=tuple(sorted(distinctive)),
    )
