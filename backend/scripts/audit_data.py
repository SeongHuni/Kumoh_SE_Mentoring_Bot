from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.app.config import REPOSITORY_ROOT, get_settings
from backend.app.data_audit import DataAuditReport, audit_posts, render_markdown
from backend.app.reporting import write_text_reports
from backend.app.storage import load_posts
from backend.app.topic_rules import load_topic_catalog


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RAG 원본 데이터의 최신성과 분류를 감사합니다."
    )
    parser.add_argument(
        "--posts",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--topic-rules",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "audit" / "reports",
    )
    parser.add_argument("--stale-after-days", type=int, default=180)
    parser.add_argument("--required-source", action="append", default=None)
    args = parser.parse_args(argv)
    if args.posts is None or args.topic_rules is None:
        settings = get_settings()
        if args.posts is None:
            args.posts = settings.raw_posts_path
        if args.topic_rules is None:
            args.topic_rules = settings.topic_rules_path
    return args


def run_audit(args: argparse.Namespace) -> DataAuditReport:
    required_sources = tuple(args.required_source or ("kumoh", "seboard"))
    return audit_posts(
        load_posts(args.posts),
        catalog=load_topic_catalog(args.topic_rules),
        required_sources=required_sources,
        stale_after_days=args.stale_after_days,
    )


def write_reports(report: DataAuditReport, output_dir: Path) -> None:
    write_text_reports(
        (
            (output_dir / "latest.json", report.model_dump_json(indent=2) + "\n"),
            (output_dir / "latest.md", render_markdown(report)),
        ),
        label="데이터 감사 보고서",
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_audit(args)
        write_reports(result, args.output_dir)
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"데이터 감사 오류: {exc}", file=sys.stderr)
        return 2
    print(f"게시글 {result.total_posts}건 · 품질 경고 {len(result.issues)}건")
    return 1 if result.issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
