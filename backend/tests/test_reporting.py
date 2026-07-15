from pathlib import Path

import pytest
from backend.app.reporting import write_text_reports


def test_write_text_reports_replaces_pair(tmp_path: Path) -> None:
    json_path = tmp_path / "latest.json"
    markdown_path = tmp_path / "latest.md"
    json_path.write_text("old json", encoding="utf-8")
    markdown_path.write_text("old markdown", encoding="utf-8")

    write_text_reports(
        ((json_path, "new json\n"), (markdown_path, "new markdown\n")),
        label="테스트 보고서",
    )

    assert json_path.read_text(encoding="utf-8") == "new json\n"
    assert markdown_path.read_text(encoding="utf-8") == "new markdown\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "latest.json",
        "latest.md",
    ]


def test_write_text_reports_rolls_back_when_second_commit_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    json_path = tmp_path / "latest.json"
    markdown_path = tmp_path / "latest.md"
    json_path.write_text("old json", encoding="utf-8")
    markdown_path.write_text("old markdown", encoding="utf-8")
    original_replace = Path.replace
    failed = False

    def fail_markdown(self: Path, target: Path) -> Path:
        nonlocal failed
        if not failed and self.suffix == ".tmp" and Path(target).name == "latest.md":
            failed = True
            raise OSError("second commit failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_markdown)

    with pytest.raises(OSError, match="second commit failed"):
        write_text_reports(
            ((json_path, "new json"), (markdown_path, "new markdown")),
            label="테스트 보고서",
        )

    assert json_path.read_text(encoding="utf-8") == "old json"
    assert markdown_path.read_text(encoding="utf-8") == "old markdown"
