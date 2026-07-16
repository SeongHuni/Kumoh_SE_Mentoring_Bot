from dataclasses import FrozenInstanceError

import pytest
from backend.app.intent_analysis import IntentOption
from backend.app.query_intent import QueryIntent
from backend.app.query_planner import QueryPlan, build_query_plan


def confirmed_intent(intent_key: str = "registration.main") -> IntentOption:
    return IntentOption(
        topic_key="registration",
        intent_key=intent_key,
        label="일반 수강신청 일정과 공지",
        example="2026학년도 수강신청 일정과 유의사항",
    )


def query_intent(**updates: object) -> QueryIntent:
    values: dict[str, object] = {
        "topic_key": "registration",
        "requested_year": 2026,
        "requested_term": "second",
        "recency_requested": True,
        "match_terms": ("공지", "수강신청"),
        "distinctive_terms": ("수강신청",),
    }
    values.update(updates)
    return QueryIntent(**values)


def test_query_plan_preserves_normalized_original_and_temporal_constraints() -> None:
    plan = build_query_plan(
        "  2026학년도   최근 수강신청 공지  ",
        confirmed_intent(),
        query_intent(),
    )

    assert isinstance(plan, QueryPlan)
    assert plan.original == "2026학년도 최근 수강신청 공지"
    assert plan.queries[0] == plan.original
    assert any("2026" in query and "2학기" in query for query in plan.queries)
    assert any(
        "일반 수강신청 일정과 공지" in query and "공식 공지" in query
        for query in plan.queries
    )


def test_hypothetical_notice_is_valid_deterministic_title_and_body() -> None:
    plan = build_query_plan(
        "수강신청 공지",
        confirmed_intent(),
        query_intent(requested_year=None, requested_term="summer"),
    )

    assert plan.hypothetical_notice.startswith("제목:")
    assert "본문:" in plan.hypothetical_notice
    assert "일반 수강신청 일정과 공지" in plan.hypothetical_notice
    assert "2026학년도 수강신청 일정과 유의사항" in plan.hypothetical_notice
    assert "여름 계절학기" in plan.hypothetical_notice
    assert plan == build_query_plan(
        "수강신청 공지",
        confirmed_intent(),
        query_intent(requested_year=None, requested_term="summer"),
    )


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("first", "1학기"),
        ("second", "2학기"),
        ("summer", "여름 계절학기"),
        ("winter", "겨울 계절학기"),
    ],
)
def test_query_plan_maps_academic_terms_to_clear_korean(term: str, expected: str) -> None:
    plan = build_query_plan(
        "학사 공지",
        IntentOption("general", "general.recent", "전체 최신 공지", "최근 학과 공지 안내"),
        query_intent(
            topic_key="general",
            requested_year=None,
            requested_term=term,
            recency_requested=True,
        ),
    )

    assert expected in plan.queries[1]
    assert expected in plan.hypothetical_notice


def test_query_plan_stably_deduplicates_queries() -> None:
    plan = build_query_plan("최근 수강신청 공지", confirmed_intent(), query_intent())

    assert plan.queries == tuple(dict.fromkeys(plan.queries))
    assert plan.queries == build_query_plan(
        "최근 수강신청 공지", confirmed_intent(), query_intent()
    ).queries


def test_query_plan_rejects_blank_question_and_topic_mismatch() -> None:
    with pytest.raises(ValueError, match="question"):
        build_query_plan("  \n", confirmed_intent(), query_intent())

    with pytest.raises(ValueError, match="topic"):
        build_query_plan(
            "최근 수강신청 공지",
            confirmed_intent(),
            query_intent(topic_key="career"),
        )


def test_query_plan_is_frozen() -> None:
    plan = build_query_plan("최근 수강신청 공지", confirmed_intent(), query_intent())

    with pytest.raises(FrozenInstanceError):
        plan.original = "변경"  # type: ignore[misc]
