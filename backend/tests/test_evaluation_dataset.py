from collections import Counter

from backend.app.config import REPOSITORY_ROOT
from backend.app.evaluation import load_evaluation_cases

EXPECTED_CASE_IDS = (
    "course-openings-current",
    "course-openings-lookup",
    "course-openings-available",
    "course-openings-2026-first",
    "registration-recent",
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
    "범위 밖": "general",
}

EXPECTED_GROUNDED_CASE_IDS = {
    "course-openings-current",
    "course-openings-lookup",
    "course-openings-available",
    "registration-early-employment",
    "capstone-plan",
    "capstone-apply",
    "capstone-schedule",
    "career-faculty-lecture",
    "career-recruitment",
    "scholarship-bootcamp",
    "general-ax-project",
    "general-recent-department",
    "general-software-notice",
}

EXPECTED_SOURCE_TITLE_FRAGMENTS = {
    "course-openings-current": ["수강신청 안내"],
    "course-openings-lookup": ["수강신청 안내"],
    "course-openings-available": ["수강신청 안내"],
    "registration-early-employment": ["조기취업자 출석인정신청"],
    "capstone-plan": ["캡스톤 디자인 운영 계획"],
    "capstone-apply": ["캡스톤 디자인 운영 계획"],
    "capstone-schedule": ["캡스톤 디자인 운영 계획"],
    "career-faculty-lecture": ["전임교원 초빙 공개강의"],
    "career-recruitment": ["전임교원 초빙"],
    "scholarship-bootcamp": ["방산AI인재양성부트캠프"],
    "general-ax-project": ["AX 기반 역량 강화 프로젝트"],
}


def test_evaluation_dataset_has_structured_30_case_baseline() -> None:
    cases = load_evaluation_cases(REPOSITORY_ROOT / "data/evaluation/questions.json")

    categories = Counter(case.category for case in cases)

    assert tuple(case.id for case in cases) == EXPECTED_CASE_IDS
    assert categories == EXPECTED_CATEGORY_COUNTS
    assert all(case.expected_latest_only is True for case in cases)


def test_evaluation_dataset_preserves_normative_expectations() -> None:
    cases = load_evaluation_cases(REPOSITORY_ROOT / "data/evaluation/questions.json")

    for case in cases:
        assert case.expected_topic_key == EXPECTED_TOPIC_BY_CATEGORY[case.category]
        assert case.expected_grounded is (case.id in EXPECTED_GROUNDED_CASE_IDS)
        assert case.expected_source_title_contains == EXPECTED_SOURCE_TITLE_FRAGMENTS.get(
            case.id, []
        )
