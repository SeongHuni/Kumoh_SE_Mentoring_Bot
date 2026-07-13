from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import NamedTemporaryFile

from backend.app.config import REPOSITORY_ROOT, get_settings
from backend.app.evaluation import (
    build_evaluation_report,
    evaluate_cases,
    load_evaluation_cases,
    render_markdown,
)
from backend.app.provider_factory import (
    create_provider,
    effective_models,
    selected_provider_name,
)
from backend.app.rag import RAGService
from backend.app.storage import load_posts
from backend.app.topic_classifier import enrich_posts
from backend.app.topic_rules import load_topic_catalog
from backend.app.vector_store import ChromaVectorStore


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SE Mentor Bot 평가를 실행하고 최신 보고서를 생성합니다."
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "evaluation" / "questions.json",
        help="평가 질문 JSON 파일 경로",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "evaluation" / "reports",
        help="평가 보고서 출력 디렉터리",
    )
    parser.add_argument(
        "--provider",
        choices=("local", "configured"),
        default="local",
        help="평가에 사용할 provider 선택",
    )
    parser.add_argument(
        "--minimum-cases",
        type=int,
        default=30,
        help="평가를 허용할 최소 케이스 수",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="실행할 평가 케이스 최대 개수",
    )
    return parser.parse_args(argv)


def validate_minimum_cases(case_count: int, minimum: int) -> None:
    if minimum < 1:
        raise ValueError("minimum-cases는 1 이상이어야 합니다.")
    if case_count < minimum:
        raise ValueError(f"평가 질문은 최소 {minimum}개가 필요합니다: {case_count}개")


def validate_indexed_chunks(indexed_chunks: int) -> None:
    if indexed_chunks < 1:
        raise ValueError("벡터 인덱스가 비어 있습니다. 재인덱싱을 먼저 실행하세요.")


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=str(target.parent),
        suffix=".tmp",
    ) as handle:
        handle.write(content)
        temporary_path = Path(handle.name)
    temporary_path.replace(target)


def write_reports(report, output_dir: Path) -> tuple[Path, Path]:
    json_path = output_dir / "latest.json"
    markdown_path = output_dir / "latest.md"
    _atomic_write(json_path, report.model_dump_json(indent=2) + "\n")
    _atomic_write(markdown_path, render_markdown(report))
    return json_path, markdown_path


def print_summary(report) -> None:
    summary = report.summary
    print(f"총 {summary.total}건 · 통과 {summary.passed}건 · 실패 {summary.failed}건")
    print(f"프로바이더: {report.provider} · 청크: {report.indexed_chunks}")


def run_evaluation(args: argparse.Namespace):
    settings = get_settings()
    effective_settings = (
        replace(settings, ai_provider="local")
        if args.provider == "local"
        else settings
    )

    cases = load_evaluation_cases(args.questions)
    validate_minimum_cases(case_count=len(cases), minimum=args.minimum_cases)
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("limit은 1 이상이어야 합니다.")
        cases = cases[: args.limit]

    catalog = load_topic_catalog(effective_settings.topic_rules_path)
    posts = enrich_posts(load_posts(effective_settings.raw_posts_path), catalog)
    vector_store = ChromaVectorStore(
        effective_settings.chroma_path,
        effective_settings.chroma_collection,
    )
    indexed_chunks = vector_store.count()
    validate_indexed_chunks(indexed_chunks)

    provider = create_provider(effective_settings)
    service = RAGService(
        provider=provider,
        vector_store=vector_store,
        top_k=effective_settings.rag_top_k,
        min_score=effective_settings.rag_min_score,
        topic_catalog=catalog,
        posts=posts,
    )
    results = evaluate_cases(cases, catalog=catalog, posts=posts, ask=service.ask)
    chat_model, embedding_model = effective_models(effective_settings)
    return build_evaluation_report(
        results,
        provider=selected_provider_name(effective_settings),
        chat_model=chat_model,
        embedding_model=embedding_model,
        indexed_chunks=indexed_chunks,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_evaluation(args)
        write_reports(report, args.output_dir)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"평가 실행 오류: {exc}", file=sys.stderr)
        return 2

    print_summary(report)
    return 1 if report.summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
