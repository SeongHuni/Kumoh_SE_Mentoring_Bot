from __future__ import annotations

from typing import Literal, TypeAlias, cast

CategoryLabel: TypeAlias = Literal[
    "수업",
    "학적·졸업",
    "장학금",
    "취업·진로",
    "비교과·행사",
    "연구·캡스톤",
    "대학원",
    "학생회",
    "행정·안내",
    "기타",
]

CATEGORY_KEY_BY_LABEL: dict[CategoryLabel, str] = {
    "수업": "course",
    "학적·졸업": "academic",
    "장학금": "scholarship",
    "취업·진로": "career",
    "비교과·행사": "extracurricular",
    "연구·캡스톤": "research_capstone",
    "대학원": "graduate",
    "학생회": "student_council",
    "행정·안내": "administration",
    "기타": "other",
}

CATEGORY_LABELS: tuple[CategoryLabel, ...] = tuple(CATEGORY_KEY_BY_LABEL)


def normalize_category_label(value: str) -> CategoryLabel:
    cleaned = " ".join(value.split())
    if cleaned not in CATEGORY_KEY_BY_LABEL:
        raise ValueError(
            "지원하지 않는 category label입니다. "
            f"허용값: {', '.join(CATEGORY_LABELS)}"
        )
    return cast(CategoryLabel, cleaned)
