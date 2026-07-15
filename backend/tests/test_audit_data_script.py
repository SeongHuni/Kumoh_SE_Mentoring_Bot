import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.app.config import REPOSITORY_ROOT
from backend.app.data_audit import AuditIssue, DataAuditReport, TopicAuditSummary
from backend.scripts import audit_data


def report(*, issues: int) -> DataAuditReport:
    return DataAuditReport(
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
        stale_after_days=180,
        total_posts=1,
        source_counts={"kumoh": 1},
        topic_summaries=[
            TopicAuditSummary(
                topic_key="general",
                topic_label="전체",
                post_count=1,
                latest_title="공개 공지",
                latest_url="https://example.com/1",
                latest_published_at="2026-07-01",
            )
        ],
        issues=[
            AuditIssue(
                code="missing_source",
                source="seboard",
                message="source 없음",
            )
            for _ in range(issues)
        ],
    )


def test_module_help_does_not_emit_runtime_warning() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "backend.scripts.audit_data", "--help"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert b"RuntimeWarning" not in result.stderr


@pytest.mark.parametrize(("issues", "expected_exit"), [(0, 0), (1, 1)])
def test_main_writes_reports_and_returns_quality_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    issues: int,
    expected_exit: int,
) -> None:
    monkeypatch.setattr(audit_data, "run_audit", lambda _args: report(issues=issues))

    exit_code = audit_data.main(["--output-dir", str(tmp_path)])

    assert exit_code == expected_exit
    assert (tmp_path / "latest.json").is_file()
    assert (tmp_path / "latest.md").is_file()


def test_main_returns_two_without_replacing_report_on_input_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    json_path = tmp_path / "latest.json"
    json_path.write_text("old", encoding="utf-8")

    def fail(_args):
        raise ValueError("감사 입력 오류")

    monkeypatch.setattr(audit_data, "run_audit", fail)

    assert audit_data.main(["--output-dir", str(tmp_path)]) == 2
    assert json_path.read_text(encoding="utf-8") == "old"
    assert not (tmp_path / "latest.md").exists()
