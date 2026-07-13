from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CASE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    question: str = Field(min_length=2, max_length=500)
    category: str
    expected_topic_key: str
    expected_grounded: bool
    expected_latest_only: bool
    expected_source_title_contains: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator(
        "id",
        "question",
        "category",
        "expected_topic_key",
        "notes",
        mode="before",
    )
    @classmethod
    def strip_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not CASE_ID_PATTERN.fullmatch(value):
            raise ValueError("평가 id는 kebab-case여야 합니다.")
        return value

    @field_validator("category", "expected_topic_key")
    @classmethod
    def reject_blank_required_strings(cls, value: str) -> str:
        if not value:
            raise ValueError("필수 문자열은 비어 있을 수 없습니다.")
        return value

    @field_validator("expected_source_title_contains")
    @classmethod
    def normalize_title_fragments(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("source 제목 기대값은 비어 있을 수 없습니다.")
        return normalized

    @model_validator(mode="after")
    def reject_contradictory_source_expectation(self) -> EvaluationCase:
        if not self.expected_grounded and self.expected_source_title_contains:
            raise ValueError("grounded=false에는 source 제목 기대값을 둘 수 없습니다.")
        return self


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    if not path.exists():
        raise FileNotFoundError(f"평가 질문 파일이 없습니다: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("평가 질문은 비어 있지 않은 JSON 배열이어야 합니다.")
    cases = [EvaluationCase.model_validate(item) for item in payload]
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("중복 평가 id가 있습니다.")
    return cases
