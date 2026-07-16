from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from backend.app.intent_analysis import (
    IntentAnalysis,
    IntentOption,
    analyze_intents,
    validate_confirmation,
)
from backend.app.schemas import ChatRequest, ChatResponse, ClarificationOption
from backend.app.topic_rules import load_topic_catalog
from pydantic import ValidationError


@pytest.fixture
def catalog():
    return load_topic_catalog(Path("data/topic_rules.json"))


def test_intent_contract_dataclasses_are_frozen() -> None:
    option = IntentOption("general", "general.recent", "최근 공지", "최근 공지")
    analysis = IntentAnalysis(option, (option,))

    with pytest.raises(FrozenInstanceError):
        option.label = "변경"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        analysis.primary = option  # type: ignore[misc]


def test_registration_question_offers_precise_sibling_intents(catalog) -> None:
    analysis = analyze_intents("최근 수강신청 공지를 알려줘", catalog)

    assert analysis.primary.intent_key == "registration.main"
    assert [item.intent_key for item in analysis.options] == [
        "registration.main",
        "registration.change",
        "registration.course_basket",
    ]


def test_exact_matched_intent_is_first_and_siblings_are_stable(catalog) -> None:
    analysis = analyze_intents("수강꾸러미 신청 안내", catalog)

    assert analysis.primary.intent_key == "registration.course_basket"
    assert [item.intent_key for item in analysis.options] == [
        "registration.course_basket",
        "registration.change",
        "registration.attendance",
    ]


def test_department_description_prefers_overview_and_offers_recent(catalog) -> None:
    analysis = analyze_intents("소프트웨어 공학과 소개를 알려줘", catalog)

    assert analysis.primary.intent_key == "department.overview"
    assert "general.recent" in [item.intent_key for item in analysis.options]


def test_unknown_general_question_falls_back_to_recent_not_department(catalog) -> None:
    analysis = analyze_intents("오늘 점심은 무엇을 먹을까?", catalog)

    assert analysis.primary.intent_key == "general.recent"
    assert analysis.primary.intent_key != "department.overview"
    assert analysis.options


def test_limit_must_be_positive_and_options_are_bounded(catalog) -> None:
    analysis = analyze_intents("최근 수강신청 공지를 알려줘", catalog, limit=2)

    assert len(analysis.options) == 2
    with pytest.raises(ValueError, match="limit"):
        analyze_intents("최근 공지 알려줘", catalog, limit=0)
    with pytest.raises(ValueError, match="limit"):
        analyze_intents("최근 공지 알려줘", catalog, limit=-1)


def test_validate_confirmation_only_returns_an_offered_option(catalog) -> None:
    analysis = analyze_intents("최근 수강신청 공지를 알려줘", catalog)

    assert validate_confirmation(analysis, "registration.main") == analysis.primary
    assert validate_confirmation(analysis, "career.general") is None


def test_chat_request_trims_confirmed_intent_and_rejects_blank() -> None:
    request = ChatRequest(
        question=" 최근 공지 알려줘 ",
        confirmed_intent_key=" registration.main ",
    )

    assert request.question == "최근 공지 알려줘"
    assert request.confirmed_intent_key == "registration.main"
    with pytest.raises(ValidationError):
        ChatRequest(question="최근 공지 알려줘", confirmed_intent_key="   ")
    with pytest.raises(ValidationError):
        ChatRequest(question="최근 공지 알려줘", confirmed_intent_key="x" * 101)


def test_chat_response_preserves_existing_constructor_defaults() -> None:
    response = ChatResponse(answer="답변", sources=[], grounded=False)

    assert response.response_type == "answer"
    assert response.interpreted_intent is None
    assert response.clarification_options == []
    assert response.suggested_questions == []
    assert response.recent_notices == []


def test_clarification_option_exposes_structured_intent_fields() -> None:
    option = ClarificationOption(
        topic_key="registration",
        intent_key="registration.main",
        label="일반 수강신청",
        example="수강신청 일정",
    )

    assert option.model_dump() == {
        "topic_key": "registration",
        "intent_key": "registration.main",
        "label": "일반 수강신청",
        "example": "수강신청 일정",
    }
