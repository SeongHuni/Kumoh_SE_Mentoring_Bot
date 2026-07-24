from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher

_WORD = re.compile(r"[가-힣A-Za-z0-9+#/]+")
_PARTICLE_SUFFIXES = (
    "으로",
    "에서",
    "에게",
    "하는",
    "한다",
    "했다",
    "하다",
    "에는",
    "처럼",
    "부터",
    "까지",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "와",
    "과",
    "로",
)


def _normalized_terms(value: str) -> frozenset[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    terms: set[str] = set()
    for raw_term in _WORD.findall(normalized):
        term = raw_term
        for suffix in _PARTICLE_SUFFIXES:
            if term.endswith(suffix) and len(term) - len(suffix) >= 2:
                term = term[: -len(suffix)]
                break
        if len(term) >= 2:
            terms.add(term)
    return frozenset(terms)


def _compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(_WORD.findall(normalized))


def _is_heading(value: str) -> bool:
    return not any(mark in value for mark in ".!?") and len(_normalized_terms(value)) <= 3


def _is_semantic_duplicate(candidate: str, reference: str) -> bool:
    candidate_terms = _normalized_terms(candidate)
    reference_terms = _normalized_terms(reference)
    if min(len(candidate_terms), len(reference_terms)) < 3:
        return False

    shared_terms = len(candidate_terms & reference_terms)
    containment = shared_terms / min(len(candidate_terms), len(reference_terms))
    candidate_compact = _compact(candidate)
    reference_compact = _compact(reference)
    character_similarity = SequenceMatcher(
        None,
        candidate_compact,
        reference_compact,
        autojunk=False,
    ).ratio()

    return containment >= 0.85 or (
        shared_terms >= 4 and containment >= 0.6 and character_similarity >= 0.55
    )


def _content_units(content: str) -> list[str]:
    return [line.strip() for line in content.splitlines() if line.strip()]


def remove_semantic_duplicates(
    content: str,
    reference_contents: Iterable[str],
) -> str:
    """Drop near-duplicate meaning units while retaining headings and unique context."""
    reference_units = [
        unit
        for reference_content in reference_contents
        for unit in _content_units(reference_content)
        if not _is_heading(unit)
    ]
    retained: list[str] = []
    seen_units: list[str] = []
    for unit in _content_units(content):
        if _is_heading(unit):
            retained.append(unit)
            continue
        if any(
            _is_semantic_duplicate(unit, other)
            for other in (*reference_units, *seen_units)
        ):
            continue
        retained.append(unit)
        seen_units.append(unit)

    return "\n".join(retained) or content
