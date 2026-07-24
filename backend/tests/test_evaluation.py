import json
from datetime import UTC, datetime

import pytest
from backend.app.domain import AnswerSource, BoardPost
from backend.app.evaluation import (
    EvaluationCase,
    EvaluationChecks,
    EvaluationMetric,
    EvaluationResult,
    build_evaluation_report,
    evaluate_cases,
    load_evaluation_cases,
    render_markdown,
)
from backend.app.schemas import ChatResponse, ClarificationOption
from backend.app.topic_rules import IntentRule, TopicCatalog, TopicRule


def valid_case(case_id: str = "course-openings-current") -> dict[str, object]:
    return {
        "id": case_id,
        "question": "이번 학기 개설강좌를 알려줘",
        "category": "개설강좌",
        "expected_topic_key": "course_openings",
        "confirmed_intent_key": "course_openings.lookup",
        "expected_intent_key": "course_openings.lookup",
        "expected_grounded": True,
        "expected_latest_only": True,
        "expected_source_title_contains": ["수강신청 안내"],
        "notes": "현재 저장 데이터 기준",
    }


def catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule(
                key="course_openings",
                label="개설강좌",
                keywords=("개설강좌",),
                suggested_questions=(),
                intents=(
                    IntentRule(
                        "course_openings.lookup",
                        "개설강좌 조회",
                        ("개설강좌",),
                        ("개설강좌",),
                        (),
                        "개설강좌 조회",
                    ),
                ),
            ),
            TopicRule(
                key="general",
                label="일반",
                keywords=(),
                suggested_questions=(),
                intents=(
                    IntentRule(
                        "general.recent",
                        "전체 최신 공지",
                        ("공지",),
                        ("공지",),
                        (),
                        "최근 공지",
                    ),
                ),
            ),
        ),
    )


def post(
    post_id: str,
    topic_key: str | None,
    latest: bool,
    *,
    intent_key: str | None = None,
) -> BoardPost:
    return BoardPost(
        id=post_id,
        source="학과 공지",
        title=f"{post_id} 수강신청 안내",
        content="개설강좌 조회 안내",
        published_at="2026-03-20" if latest else "2026-03-10",
        url=f"https://example.com/{post_id}",
        topic_key=topic_key,
        topic_label="개설강좌" if topic_key == "course_openings" else "일반",
        intent_key=intent_key
        or (
            "course_openings.lookup"
            if topic_key == "course_openings"
            else "general.recent"
        ),
        is_latest_topic=latest,
    )


def response(
    grounded: bool,
    url: str | None = None,
    title: str = "",
    *,
    intent_key: str = "course_openings.lookup",
    topic_key: str = "course_openings",
) -> ChatResponse:
    sources = (
        [
            AnswerSource(
                title=title,
                url=url,
                source="학과 공지",
                published_at="2026-03-20",
                score=0.9,
            )
        ]
        if url is not None
        else []
    )
    return ChatResponse(
        response_type="answer" if grounded else "no_answer",
        answer="답변",
        sources=sources,
        grounded=grounded,
        interpreted_intent=ClarificationOption(
            topic_key=topic_key,
            intent_key=intent_key,
            label="평가 의도",
            example="평가 예시",
        ),
    )


def test_load_evaluation_cases_validates_structured_list(tmp_path) -> None:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps([valid_case()], ensure_ascii=False), encoding="utf-8")

    cases = load_evaluation_cases(path)

    assert cases == [EvaluationCase.model_validate(valid_case())]


def test_evaluation_case_requires_confirmed_and_expected_intent() -> None:
    payload = valid_case("intent-contract")
    payload["confirmed_intent_key"] = "course_openings.lookup"
    payload["expected_intent_key"] = "course_openings.lookup"

    case = EvaluationCase.model_validate(payload)

    assert case.confirmed_intent_key == "course_openings.lookup"
    assert case.expected_intent_key == "course_openings.lookup"


def test_evaluation_rejects_source_from_other_subintent() -> None:
    intent_catalog = TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule(
                "registration",
                "수강신청",
                ("수강신청",),
                (),
                intents=(
                    IntentRule(
                        "registration.main",
                        "일반 수강신청",
                        ("수강신청",),
                        ("수강신청",),
                        ("출석인정",),
                        "수강신청 일정",
                    ),
                    IntentRule(
                        "registration.attendance",
                        "출석인정",
                        ("출석인정",),
                        ("출석인정",),
                        (),
                        "출석인정 신청",
                    ),
                ),
            ),
            TopicRule("general", "일반", (), ()),
        ),
    )
    attendance = BoardPost(
        id="attendance",
        source="학과 공지",
        title="조기취업자 출석인정신청 안내",
        content="출석인정 신청",
        published_at="2026-06-16",
        url="https://example.com/attendance",
        topic_key="registration",
        topic_label="수강신청",
        intent_key="registration.attendance",
        is_latest_topic=True,
    )
    payload = valid_case("wrong-subintent")
    payload.update(
        question="최근 수강신청 공지를 알려줘",
        category="수강신청",
        expected_topic_key="registration",
        confirmed_intent_key="registration.main",
        expected_intent_key="registration.main",
        expected_source_title_contains=[],
    )
    actual = ChatResponse(
        response_type="answer",
        answer="출석인정 안내",
        sources=[
            AnswerSource(
                title=attendance.title,
                url=attendance.url,
                source=attendance.source,
                published_at=attendance.published_at,
                score=0.9,
            )
        ],
        grounded=True,
        interpreted_intent=ClarificationOption(
            topic_key="registration",
            intent_key="registration.main",
            label="일반 수강신청",
            example="수강신청 일정",
        ),
    )

    result = evaluate_cases(
        [EvaluationCase.model_validate(payload)],
        catalog=intent_catalog,
        posts=[attendance],
        ask=lambda _question, _intent: actual,
    )[0]

    assert result.checks.intent_match is False
    assert any("intent" in failure for failure in result.failures)


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


def test_case_rejects_unknown_fields() -> None:
    payload = valid_case()
    payload["expected_source_title_contians"] = ["수강신청 안내"]

    with pytest.raises(ValueError, match="expected_source_title_contians"):
        EvaluationCase.model_validate(payload)


@pytest.mark.parametrize(
    "invalid_value",
    [
        pytest.param("false", id="string-false"),
        pytest.param(1, id="integer-one"),
    ],
)
def test_case_rejects_non_boolean_expected_grounded(invalid_value: object) -> None:
    payload = valid_case()
    payload["expected_grounded"] = invalid_value
    payload["expected_source_title_contains"] = []

    with pytest.raises(ValueError, match="expected_grounded"):
        EvaluationCase.model_validate(payload)


@pytest.mark.parametrize("case_id", ["Upper-Case", "space id", "한글-id", ""])
def test_case_requires_kebab_case_id(case_id: str) -> None:
    payload = valid_case(case_id)

    with pytest.raises(ValueError):
        EvaluationCase.model_validate(payload)


def test_evaluate_cases_passes_matching_latest_source() -> None:
    latest_post = post("latest", "course_openings", True)
    case = EvaluationCase.model_validate(valid_case())

    results = evaluate_cases(
        [case],
        catalog=catalog(),
        posts=[latest_post, post("old", "course_openings", False)],
        ask=lambda _question, _intent: response(
            True, latest_post.url, latest_post.title
        ),
    )

    assert results[0].checks == EvaluationChecks(
        topic_match=True,
        intent_match=True,
        grounded_match=True,
        latest_only_match=True,
        source_title_match=True,
    )
    assert results[0].failures == []
    assert results[0].passed is True


def test_evaluate_cases_fails_stale_source_wrong_title_and_grounding() -> None:
    stale_post = post("old", "course_openings", False)
    case = EvaluationCase.model_validate(valid_case())

    result = evaluate_cases(
        [case],
        catalog=catalog(),
        posts=[post("latest", "course_openings", True), stale_post],
        ask=lambda _question, _intent: response(False, stale_post.url, "다른 공지"),
    )[0]

    assert result.checks.grounded_match is False
    assert result.checks.latest_only_match is False
    assert result.checks.source_title_match is False
    assert any("grounded" in failure for failure in result.failures)
    assert any("최신" in failure for failure in result.failures)
    assert any("source 제목" in failure for failure in result.failures)
    assert result.passed is False


def test_evaluate_cases_classifies_topic_and_reports_forced_mismatch() -> None:
    matching = valid_case("topic-match")
    matching.update(
        expected_grounded=False,
        expected_latest_only=False,
        expected_source_title_contains=[],
    )
    mismatch = valid_case("topic-mismatch")
    mismatch.update(
        question="학과 소식을 알려줘",
        expected_grounded=False,
        expected_latest_only=False,
        expected_source_title_contains=[],
    )

    results = evaluate_cases(
        [
            EvaluationCase.model_validate(matching),
            EvaluationCase.model_validate(mismatch),
        ],
        catalog=catalog(),
        posts=[],
        ask=lambda _question, _intent: response(False),
    )

    assert results[0].actual_topic_key == "course_openings"
    assert results[0].checks.topic_match is True
    assert results[1].actual_topic_key == "general"
    assert results[1].checks.topic_match is False
    assert any("topic 기대값 불일치" in failure for failure in results[1].failures)


def test_evaluate_cases_rejects_unknown_expected_topic() -> None:
    payload = valid_case("unknown-topic")
    payload["expected_topic_key"] = "missing"

    with pytest.raises(ValueError, match="존재하지 않는 topic"):
        evaluate_cases(
            [EvaluationCase.model_validate(payload)],
            catalog=catalog(),
            posts=[],
            ask=lambda _question, _intent: response(True),
        )


def test_evaluate_cases_preflights_all_topics_before_asking() -> None:
    valid_payload = valid_case("valid-first")
    invalid_payload = valid_case("invalid-second")
    invalid_payload["expected_topic_key"] = "missing"
    cases = (
        EvaluationCase.model_validate(payload)
        for payload in (valid_payload, invalid_payload)
    )
    ask_calls = 0

    def ask(_: str, _intent: str) -> ChatResponse:
        nonlocal ask_calls
        ask_calls += 1
        return response(True)

    with pytest.raises(ValueError, match="존재하지 않는 topic"):
        evaluate_cases(
            cases,
            catalog=catalog(),
            posts=[],
            ask=ask,
        )

    assert ask_calls == 0


def test_evaluate_cases_scopes_latest_urls_for_general_and_specific_topics() -> None:
    general_payload = valid_case("general-latest")
    general_payload.update(
        question="학과 소식을 알려줘",
        expected_topic_key="general",
        confirmed_intent_key="general.recent",
        expected_intent_key="general.recent",
        expected_source_title_contains=[],
    )
    course_payload = valid_case("course-specific-latest")
    course_payload["expected_source_title_contains"] = []
    other_latest = post("other-latest", "other_topic", True)

    results = evaluate_cases(
        [
            EvaluationCase.model_validate(general_payload),
            EvaluationCase.model_validate(course_payload),
        ],
        catalog=catalog(),
        posts=[other_latest],
        ask=lambda question, _intent: response(
            True,
            other_latest.url,
            other_latest.title,
            intent_key=(
                "general.recent" if "학과" in question else "course_openings.lookup"
            ),
            topic_key="general" if "학과" in question else "course_openings",
        ),
    )

    assert results[0].checks.latest_only_match is True
    assert results[0].passed is True
    assert results[1].checks.latest_only_match is False
    assert "해당 intent의 최신 source가 아닌 URL이 포함됐습니다." in results[1].failures


def test_evaluate_cases_allows_latest_categorized_source_for_general_recent() -> None:
    payload = valid_case("general-cross-topic-latest")
    payload.update(
        question="최근 학과 공지를 알려줘",
        expected_topic_key="general",
        confirmed_intent_key="general.recent",
        expected_intent_key="general.recent",
        expected_source_title_contains=[],
    )
    categorized_latest = post(
        "course-latest",
        "course_openings",
        True,
        intent_key="course_openings.lookup",
    )

    result = evaluate_cases(
        [EvaluationCase.model_validate(payload)],
        catalog=catalog(),
        posts=[categorized_latest],
        ask=lambda _question, _intent: response(
            True,
            categorized_latest.url,
            categorized_latest.title,
            intent_key="general.recent",
            topic_key="general",
        ),
    )[0]

    assert result.checks.intent_match is True
    assert result.checks.latest_only_match is True
    assert result.passed is True


def test_build_evaluation_report_excludes_inapplicable_checks() -> None:
    results = [
        EvaluationResult(
            case_id="failed-case",
            question="질문",
            category="일반",
            expected_topic_key="general",
            actual_topic_key="general",
            confirmed_intent_key="general.recent",
            expected_intent_key="general.recent",
            actual_intent_key="general.recent",
            expected_grounded=False,
            actual_grounded=False,
            sources=[],
            checks=EvaluationChecks(
                topic_match=True,
                intent_match=True,
                grounded_match=True,
                latest_only_match=True,
                source_title_match=None,
            ),
            failures=["최신 source 실패"],
            passed=False,
        ),
        EvaluationResult(
            case_id="passed-case",
            question="다른 질문",
            category="일반",
            expected_topic_key="general",
            actual_topic_key="general",
            confirmed_intent_key="general.recent",
            expected_intent_key="general.recent",
            actual_intent_key="general.recent",
            expected_grounded=False,
            actual_grounded=False,
            sources=[],
            checks=EvaluationChecks(
                topic_match=True,
                intent_match=True,
                grounded_match=True,
                latest_only_match=None,
                source_title_match=None,
            ),
            failures=[],
            passed=True,
        ),
    ]

    report = build_evaluation_report(
        results,
        provider="local",
        chat_model="local-chat",
        embedding_model="local-embedding",
        indexed_chunks=12,
        generated_at=datetime(2026, 3, 20, tzinfo=UTC),
    )

    assert report.summary.total == 2
    assert report.summary.passed == 1
    assert report.summary.failed == 1
    assert report.summary.latest_only == EvaluationMetric(
        passed=1,
        total=1,
        rate=1.0,
    )
    assert report.summary.source_title == EvaluationMetric(
        passed=0,
        total=0,
        rate=None,
    )
    assert report.summary.intent == EvaluationMetric(passed=2, total=2, rate=1.0)


def test_render_markdown_lists_summary_case_and_failure_reason() -> None:
    failure_reason = "topic 기대값 불일치: expected=course_openings, actual=general"
    result = EvaluationResult(
        case_id="topic-mismatch",
        question="학과 소식을 알려줘",
        category="개설강좌",
        expected_topic_key="course_openings",
        actual_topic_key="general",
        confirmed_intent_key="course_openings.lookup",
        expected_intent_key="course_openings.lookup",
        actual_intent_key="course_openings.lookup",
        expected_grounded=False,
        actual_grounded=False,
        sources=[],
        checks=EvaluationChecks(
            topic_match=False,
            intent_match=True,
            grounded_match=True,
            latest_only_match=None,
            source_title_match=None,
        ),
        failures=[failure_reason],
        passed=False,
    )
    report = build_evaluation_report(
        [result],
        provider="local",
        chat_model="local-chat",
        embedding_model="local-embedding",
        indexed_chunks=0,
        generated_at=datetime(2026, 3, 20, tzinfo=UTC),
    )

    markdown = render_markdown(report)

    assert "총 1건 · 통과 0건 · 실패 1건" in markdown
    assert "### [FAIL] topic-mismatch" in markdown
    assert (
        "topic 기대값 불일치: expected=course\\_openings, actual=general" in markdown
    )
    assert markdown.endswith("\n")
    assert not markdown.endswith("\n\n")


def test_render_markdown_sanitizes_dynamic_content() -> None:
    result = EvaluationResult(
        case_id="case\n## injected-case *id*",
        question="질문\n# injected-question [link](https://evil.example)",
        category="일반",
        expected_topic_key="general",
        actual_topic_key="general",
        confirmed_intent_key="general.recent",
        expected_intent_key="general.recent",
        actual_intent_key="general.recent",
        expected_grounded=True,
        actual_grounded=True,
        sources=[
            AnswerSource(
                title="공지\n# injected-source *title*",
                url="https://example.com/[unsafe](path)",
                source="학과 공지",
                published_at="2026-03-20\n| injected-date |",
                score=0.9,
            )
        ],
        checks=EvaluationChecks(
            topic_match=True,
            intent_match=True,
            grounded_match=True,
            latest_only_match=None,
            source_title_match=None,
        ),
        failures=["실패\n## injected-failure *reason*"],
        passed=False,
    )
    report = build_evaluation_report(
        [result],
        provider="local\n## injected-provider *unsafe*",
        chat_model="chat_[model]",
        embedding_model="embed|model",
        indexed_chunks=1,
        generated_at=datetime(2026, 3, 20, tzinfo=UTC),
    )

    markdown = render_markdown(report)

    assert "\n# injected-" not in markdown
    assert "\n## injected-" not in markdown
    assert "\n| injected-date |" not in markdown
    assert "case \\#\\# injected-case \\*id\\*" in markdown
    assert "질문 \\# injected-question \\[link\\]\\(https://evil.example\\)" in markdown
    assert "local \\#\\# injected-provider \\*unsafe\\*" in markdown
    assert "공지 \\# injected-source \\*title\\*" in markdown
    assert "2026-03-20 \\| injected-date \\|" in markdown
    assert "https://example.com/\\[unsafe\\]\\(path\\)" in markdown
    assert "실패 \\#\\# injected-failure \\*reason\\*" in markdown
