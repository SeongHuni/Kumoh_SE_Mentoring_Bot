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
from backend.app.schemas import ChatResponse
from backend.app.topic_rules import TopicCatalog, TopicRule


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


def catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule(
                key="course_openings",
                label="개설강좌",
                keywords=("개설강좌",),
                suggested_questions=(),
            ),
            TopicRule(
                key="general",
                label="일반",
                keywords=(),
                suggested_questions=(),
            ),
        ),
    )


def post(post_id: str, topic_key: str | None, latest: bool) -> BoardPost:
    return BoardPost(
        id=post_id,
        source="학과 공지",
        title=f"{post_id} 수강신청 안내",
        content="개설강좌 조회 안내",
        published_at="2026-03-20" if latest else "2026-03-10",
        url=f"https://example.com/{post_id}",
        topic_key=topic_key,
        topic_label="개설강좌" if topic_key == "course_openings" else "일반",
        is_latest_topic=latest,
    )


def response(
    grounded: bool,
    url: str | None = None,
    title: str = "",
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
    return ChatResponse(answer="답변", sources=sources, grounded=grounded)


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
        ask=lambda _: response(True, latest_post.url, latest_post.title),
    )

    assert results[0].checks == EvaluationChecks(
        topic_match=True,
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
        ask=lambda _: response(False, stale_post.url, "다른 공지"),
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
        ask=lambda _: response(False),
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
            ask=lambda _: response(True),
        )


def test_build_evaluation_report_excludes_inapplicable_checks() -> None:
    results = [
        EvaluationResult(
            case_id="failed-case",
            question="질문",
            category="일반",
            expected_topic_key="general",
            actual_topic_key="general",
            expected_grounded=False,
            actual_grounded=False,
            sources=[],
            checks=EvaluationChecks(
                topic_match=True,
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
            expected_grounded=False,
            actual_grounded=False,
            sources=[],
            checks=EvaluationChecks(
                topic_match=True,
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


def test_render_markdown_lists_summary_case_and_failure_reason() -> None:
    failure_reason = "topic 기대값 불일치: expected=course_openings, actual=general"
    result = EvaluationResult(
        case_id="topic-mismatch",
        question="학과 소식을 알려줘",
        category="개설강좌",
        expected_topic_key="course_openings",
        actual_topic_key="general",
        expected_grounded=False,
        actual_grounded=False,
        sources=[],
        checks=EvaluationChecks(
            topic_match=False,
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
    assert failure_reason in markdown
    assert markdown.endswith("\n")
    assert not markdown.endswith("\n\n")
