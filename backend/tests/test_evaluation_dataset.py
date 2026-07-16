from collections import Counter

from backend.app.config import REPOSITORY_ROOT
from backend.app.evaluation import load_evaluation_cases

EXPECTED_CASE_IDS = (
    "course-openings-current",
    "course-openings-lookup",
    "course-openings-available",
    "course-openings-2026-first",
    "registration-recent-main",
    "registration-change",
    "registration-early-employment",
    "registration-period",
    "registration-course-change",
    "capstone-plan",
    "capstone-apply",
    "capstone-schedule",
    "capstone-second-semester",
    "career-faculty-lecture",
    "career-program",
    "career-internship",
    "career-recruitment",
    "scholarship-bootcamp",
    "scholarship-apply",
    "scholarship-selection",
    "scholarship-recent",
    "graduation-requirements",
    "graduation-certification",
    "graduation-credits",
    "general-ax-project",
    "general-recent-department",
    "general-software-notice",
    "department-overview",
    "out-of-scope-cafeteria",
    "out-of-scope-dormitory",
    "out-of-scope-weather",
)

EXPECTED_CATEGORY_COUNTS = Counter(
    {
        "개설강좌": 4,
        "수강신청": 5,
        "캡스톤": 4,
        "진로·취업": 4,
        "장학금": 4,
        "졸업요건": 3,
        "일반 공지": 3,
        "학과 소개": 1,
        "범위 밖": 3,
    }
)

EXPECTED_TOPIC_BY_CATEGORY = {
    "개설강좌": "course_openings",
    "수강신청": "registration",
    "캡스톤": "capstone",
    "진로·취업": "career",
    "장학금": "scholarship",
    "졸업요건": "graduation",
    "일반 공지": "general",
    "학과 소개": "general",
    "범위 밖": "general",
}


def cases_by_id():
    cases = load_evaluation_cases(REPOSITORY_ROOT / "data/evaluation/questions.json")
    return cases, {case.id: case for case in cases}


def test_evaluation_dataset_has_intent_aware_31_case_baseline() -> None:
    cases, _ = cases_by_id()

    assert tuple(case.id for case in cases) == EXPECTED_CASE_IDS
    assert Counter(case.category for case in cases) == EXPECTED_CATEGORY_COUNTS
    assert all(case.expected_latest_only is True for case in cases)
    assert all(case.confirmed_intent_key for case in cases)
    assert all(case.expected_intent_key for case in cases)


def test_evaluation_dataset_topics_and_intents_are_consistent() -> None:
    cases, _ = cases_by_id()

    for case in cases:
        assert case.expected_topic_key == EXPECTED_TOPIC_BY_CATEGORY[case.category]
        assert case.confirmed_intent_key == case.expected_intent_key
        if case.expected_topic_key == "general":
            assert case.expected_intent_key in {
                "general.recent",
                "department.overview",
            }
        else:
            assert case.expected_intent_key.startswith(f"{case.expected_topic_key}.")


def test_evaluation_dataset_preserves_reported_accuracy_regressions() -> None:
    _, cases = cases_by_id()

    registration = cases["registration-recent-main"]
    assert registration.question == "최근 수강신청 공지를 알려줘"
    assert registration.confirmed_intent_key == "registration.main"
    assert registration.expected_grounded is True
    assert registration.expected_source_title_contains == ["수강신청 안내"]

    overview = cases["department-overview"]
    assert overview.question == "컴퓨터 소프트웨어 공학과에 대해 알려줘"
    assert overview.confirmed_intent_key == "department.overview"
    assert overview.expected_grounded is False
    assert overview.expected_source_title_contains == []


def test_evaluation_dataset_fails_closed_without_direct_evidence() -> None:
    _, cases = cases_by_id()

    assert all(
        cases[case_id].expected_grounded is False
        for case_id in (
            "course-openings-current",
            "course-openings-lookup",
            "course-openings-available",
            "course-openings-2026-first",
            "out-of-scope-cafeteria",
            "out-of-scope-dormitory",
            "out-of-scope-weather",
        )
    )
