from collections import Counter

from backend.app.config import REPOSITORY_ROOT
from backend.app.evaluation import load_evaluation_cases


def test_evaluation_dataset_has_structured_30_case_baseline() -> None:
    cases = load_evaluation_cases(REPOSITORY_ROOT / "data/evaluation/questions.json")

    categories = Counter(case.category for case in cases)

    assert len(cases) >= 30
    assert categories["개설강좌"] >= 4
    assert categories["수강신청"] >= 5
    assert categories["캡스톤"] >= 4
    assert categories["진로·취업"] >= 4
    assert categories["장학금"] >= 4
    assert categories["졸업요건"] >= 3
    assert categories["일반 공지"] >= 3
    assert categories["범위 밖"] >= 3
    assert all(case.expected_latest_only is True for case in cases)
