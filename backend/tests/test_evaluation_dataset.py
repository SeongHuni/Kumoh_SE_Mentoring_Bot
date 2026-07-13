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

EXPECTED_QUESTIONS = (
    "이번 학기 개설강좌를 알려줘",
    "개설강좌 조회 방법은?",
    "수강 가능 과목은 어디서 확인해?",
    "2026학년도 1학기 개설 과목을 알려줘",
    "최근 수강신청 일정과 유의사항을 알려줘",
    "수강신청 변경 방법을 알려줘",
    "수강신청 후 여름계절수업 조기취업자 출석인정신청 안내를 찾아줘",
    "수강 신청 기간은 언제야?",
    "최근 수강변경 공지를 알려줘",
    "캡스톤디자인 운영 계획을 알려줘",
    "캡스톤디자인 신청 방법이 뭐야?",
    "캡스톤 디자인 일정은 언제야?",
    "2026학년도 2학기 캡스톤디자인 공지를 알려줘",
    "진로 관련 전임교원 초빙 공개강의 심사 공고를 찾아줘",
    "최근 취업 프로그램을 알려줘",
    "인턴 관련 공지가 있어?",
    "최근 채용 공지를 찾아줘",
    "장학 관련 방산AI인재양성부트캠프 설명회 공지를 찾아줘",
    "장학금 신청 공지를 알려줘",
    "장학생 선발 기준은?",
    "최근 장학 공지를 알려줘",
    "졸업요건을 확인해줘",
    "졸업인증 기준은?",
    "졸업 요건 이수학점을 알려줘",
    "AX 기반 역량 강화 프로젝트 공모 기간 연장 안내를 찾아줘",
    "최근 학과 공지를 알려줘",
    "소프트웨어전공 공지를 알려줘",
    "오늘 학생식당 메뉴를 알려줘",
    "데이터에 없는 기숙사 식단을 알려줘",
    "오늘 학교 날씨를 알려줘",
)

EXPECTED_CATEGORIES = (
    ("개설강좌",) * 4
    + ("수강신청",) * 5
    + ("캡스톤",) * 4
    + ("진로·취업",) * 4
    + ("장학금",) * 4
    + ("졸업요건",) * 3
    + ("일반 공지",) * 3
    + ("범위 밖",) * 3
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
    assert tuple(case.question for case in cases) == EXPECTED_QUESTIONS
    assert tuple(case.category for case in cases) == EXPECTED_CATEGORIES
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
