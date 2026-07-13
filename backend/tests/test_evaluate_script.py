from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.app.evaluation import (
    EvaluationChecks,
    EvaluationMetric,
    EvaluationReport,
    EvaluationResult,
    EvaluationSummary,
)
from backend.scripts import evaluate


def report(failed: int) -> EvaluationReport:
    passed = failed == 0
    grounded_failure = "grounded 기대값 불일치: expected=True, actual=False"
    result = EvaluationResult(
        case_id="course-openings-current",
        question="이번 학기 개설강좌를 알려줘",
        category="개설강좌",
        expected_topic_key="course_openings",
        actual_topic_key="course_openings",
        expected_grounded=True,
        actual_grounded=passed,
        sources=[],
        checks=EvaluationChecks(
            topic_match=True,
            grounded_match=passed,
            latest_only_match=True,
            source_title_match=None,
        ),
        failures=[] if passed else [grounded_failure],
        passed=passed,
    )
    return EvaluationReport(
        generated_at=datetime(2026, 7, 12, tzinfo=UTC),
        provider="local",
        chat_model="local-answer",
        embedding_model="local-embedding",
        indexed_chunks=79,
        summary=EvaluationSummary(
            total=1,
            passed=int(passed),
            failed=failed,
            topic=EvaluationMetric(passed=1, total=1, rate=1.0),
            grounded=EvaluationMetric(
                passed=int(passed),
                total=1,
                rate=float(passed),
            ),
            latest_only=EvaluationMetric(passed=1, total=1, rate=1.0),
            source_title=EvaluationMetric(passed=0, total=0, rate=None),
        ),
        results=[result],
    )


def test_main_writes_passing_reports_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        evaluate,
        "run_evaluation",
        lambda _args: report(failed=0),
    )

    exit_code = evaluate.main(
        ["--output-dir", str(tmp_path), "--minimum-cases", "1"]
    )

    assert exit_code == 0
    assert (tmp_path / "latest.json").is_file()
    assert (tmp_path / "latest.md").is_file()
    assert list(tmp_path.glob("*.tmp")) == []


def test_main_writes_failed_report_before_returning_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run_failed_evaluation(_args: Namespace) -> EvaluationReport:
        return report(failed=1)

    monkeypatch.setattr(evaluate, "run_evaluation", run_failed_evaluation)

    exit_code = evaluate.main(
        ["--output-dir", str(tmp_path), "--minimum-cases", "1"]
    )

    assert exit_code == 1
    assert (tmp_path / "latest.json").is_file()
    markdown = (tmp_path / "latest.md").read_text(encoding="utf-8")
    assert "grounded 기대값 불일치" in markdown


def test_main_returns_two_without_report_on_execution_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def raise_empty_index(_args: Namespace) -> EvaluationReport:
        raise ValueError("벡터 인덱스가 비어 있습니다.")

    monkeypatch.setattr(evaluate, "run_evaluation", raise_empty_index)

    exit_code = evaluate.main(
        ["--output-dir", str(tmp_path), "--minimum-cases", "1"]
    )

    assert exit_code == 2
    assert not (tmp_path / "latest.json").exists()
    assert not (tmp_path / "latest.md").exists()
    assert "평가 실행 오류: 벡터 인덱스가 비어 있습니다." in capsys.readouterr().err


def test_validate_minimum_cases_rejects_too_few_cases() -> None:
    with pytest.raises(ValueError, match="최소 30개"):
        evaluate.validate_minimum_cases(case_count=29, minimum=30)


def test_validate_indexed_chunks_rejects_empty_store() -> None:
    with pytest.raises(ValueError, match="벡터 인덱스가 비어"):
        evaluate.validate_indexed_chunks(0)
