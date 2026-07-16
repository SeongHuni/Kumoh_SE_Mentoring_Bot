from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from math import inf

from backend.app.freshness import parse_published_at
from backend.app.reranker import RerankedCandidate

GroupKey = tuple[str, str]


def _canonical_published_at(value: str | None) -> datetime | None:
    parsed = parse_published_at(value)
    return None if parsed is None else parsed.astimezone(UTC)


def _metadata(candidate: RerankedCandidate) -> tuple[str, str | None, datetime | None]:
    chunk = candidate.candidate.chunk
    return chunk.topic_key, chunk.intent_key, _canonical_published_at(
        chunk.published_at
    )


def _validate_inputs(
    candidates: Sequence[RerankedCandidate],
    require_dated: bool,
) -> None:
    if not isinstance(candidates, Sequence):
        raise TypeError("candidates must be a Sequence")
    if not isinstance(require_dated, bool):
        raise TypeError("require_dated must be a bool")
    for candidate in candidates:
        if not isinstance(candidate, RerankedCandidate):
            raise TypeError("candidates must contain RerankedCandidate items")


def _validate_metadata(candidates: Sequence[RerankedCandidate]) -> None:
    metadata_by_url: dict[str, tuple[str, str | None, datetime | None]] = {}
    for candidate in candidates:
        chunk = candidate.candidate.chunk
        metadata = _metadata(candidate)
        previous = metadata_by_url.get(chunk.url)
        if previous is not None and previous != metadata:
            raise ValueError(f"conflicting metadata for URL {chunk.url!r}")
        metadata_by_url[chunk.url] = metadata


def _group_key(candidate: RerankedCandidate) -> GroupKey:
    chunk = candidate.candidate.chunk
    if chunk.intent_key is not None:
        return ("intent", chunk.intent_key)
    return ("topic", chunk.topic_key)


def _quality_key(candidate: RerankedCandidate) -> tuple[object, ...]:
    hybrid = candidate.candidate
    return (
        -candidate.score,
        -hybrid.fused_score,
        -hybrid.signal_count,
        hybrid.dense_rank if hybrid.dense_rank is not None else inf,
        hybrid.lexical_rank if hybrid.lexical_rank is not None else inf,
        hybrid.chunk.chunk_index,
        hybrid.chunk.id,
    )


def _freshness_key(candidate: RerankedCandidate) -> tuple[object, ...]:
    published_at = _canonical_published_at(candidate.candidate.chunk.published_at)
    if published_at is None:
        date_key = (1, 0, 0, 0, 0, 0, 0, 0)
    else:
        date_key = (
            0,
            -published_at.year,
            -published_at.month,
            -published_at.day,
            -published_at.hour,
            -published_at.minute,
            -published_at.second,
            -published_at.microsecond,
        )
    return (*date_key, *_quality_key(candidate))


def select_freshest(
    candidates: Sequence[RerankedCandidate],
    *,
    require_dated: bool = False,
) -> list[RerankedCandidate]:
    _validate_inputs(candidates, require_dated)
    _validate_metadata(candidates)

    eligible = [
        candidate
        for candidate in candidates
        if not candidate.has_intent_conflict and candidate.temporal_match
    ]
    if require_dated:
        eligible = [
            candidate
            for candidate in eligible
            if _canonical_published_at(candidate.candidate.chunk.published_at)
            is not None
        ]

    strongest_by_group_url: dict[tuple[GroupKey, str], RerankedCandidate] = {}
    for candidate in eligible:
        key = (_group_key(candidate), candidate.candidate.chunk.url)
        current = strongest_by_group_url.get(key)
        if current is None or _quality_key(candidate) < _quality_key(current):
            strongest_by_group_url[key] = candidate

    newest_by_group: dict[GroupKey, RerankedCandidate] = {}
    for candidate in strongest_by_group_url.values():
        group_key = _group_key(candidate)
        current = newest_by_group.get(group_key)
        if current is None or _freshness_key(candidate) < _freshness_key(current):
            newest_by_group[group_key] = candidate

    return sorted(newest_by_group.values(), key=_freshness_key)
