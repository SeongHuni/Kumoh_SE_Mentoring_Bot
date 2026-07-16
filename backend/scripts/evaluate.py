from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from backend.app.config import REPOSITORY_ROOT, get_settings
from backend.app.evaluation import (
    EvaluationReport,
    build_evaluation_report,
    evaluate_cases,
    load_evaluation_cases,
    render_markdown,
)
from backend.app.index_manifest import assess_index_compatibility
from backend.app.provider_factory import (
    create_provider,
    effective_models,
    selected_provider_name,
)
from backend.app.rag import RAGService
from backend.app.reporting import write_text_reports
from backend.app.schemas import ChatResponse
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


def write_reports(report: EvaluationReport, output_dir: Path) -> None:
    write_text_reports(
        (
            (output_dir / "latest.json", report.model_dump_json(indent=2) + "\n"),
            (output_dir / "latest.md", render_markdown(report)),
        ),
        label="평가 보고서",
    )


def print_summary(report: EvaluationReport) -> None:
    summary = report.summary
    print(f"총 {summary.total}건 · 통과 {summary.passed}건 · 실패 {summary.failed}건")
    print(f"프로바이더: {report.provider} · 청크: {report.indexed_chunks}")


def run_evaluation(args: argparse.Namespace) -> EvaluationReport:
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
    compatibility = assess_index_compatibility(
        settings=effective_settings,
        store=vector_store,
    )
    if not compatibility.compatible:
        raise ValueError(
            "벡터 인덱스가 현재 설정과 호환되지 않습니다: "
            f"{compatibility.reason}. 인덱스를 생성할 때와 동일한 provider로 "
            "index --reset을 실행하세요."
        )

    provider = create_provider(effective_settings)
    service = RAGService(
        provider=provider,
        vector_store=vector_store,
        top_k=effective_settings.rag_top_k,
        min_score=effective_settings.rag_min_score,
        topic_catalog=catalog,
        posts=posts,
    )
    def ask_with_confirmed_intent(question: str, intent_key: str) -> ChatResponse:
        return service.ask(question, confirmed_intent_key=intent_key)

    results = evaluate_cases(
        cases,
        catalog=catalog,
        posts=posts,
        ask=ask_with_confirmed_intent,
    )
    chat_model, embedding_model = effective_models(effective_settings)
    return build_evaluation_report(
        results,
        provider=selected_provider_name(effective_settings),
        chat_model=chat_model,
        embedding_model=embedding_model,
        indexed_chunks=compatibility.indexed_chunks,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run_evaluation(args)
        write_reports(report, args.output_dir)
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"평가 실행 오류: {exc}", file=sys.stderr)
        return 2

    print_summary(report)
    return 1 if report.summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
