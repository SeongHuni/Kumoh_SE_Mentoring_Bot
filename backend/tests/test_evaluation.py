import json

import pytest
from backend.app.evaluation import EvaluationCase, load_evaluation_cases


def valid_case(case_id: str = "course-openings-current") -> dict[str, object]:
    return {
        "id": case_id,
        "question": "이번 학기 개설강좌를 알려줘",
        "category": "개설강좌",
        "expected_topic_key": "course_openings",
        "expected_grounded": True,
        "expected_latest_only": True,
        "expected_source_title_contains": ["수강신청 안내"],
        "notes": "현재 저장 데이터 기준",
    }


def test_load_evaluation_cases_validates_structured_list(tmp_path) -> None:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps([valid_case()], ensure_ascii=False), encoding="utf-8")

    cases = load_evaluation_cases(path)

    assert cases == [EvaluationCase.model_validate(valid_case())]


def test_load_evaluation_cases_rejects_duplicate_ids(tmp_path) -> None:
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps([valid_case(), valid_case()], ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="중복 평가 id"):
        load_evaluation_cases(path)


def test_case_rejects_source_expectation_when_grounded_is_false() -> None:
    payload = valid_case()
    payload["expected_grounded"] = False

    with pytest.raises(ValueError, match="grounded=false"):
        EvaluationCase.model_validate(payload)


@pytest.mark.parametrize("case_id", ["Upper-Case", "space id", "한글-id", ""])
def test_case_requires_kebab_case_id(case_id: str) -> None:
    payload = valid_case(case_id)

    with pytest.raises(ValueError):
        EvaluationCase.model_validate(payload)
