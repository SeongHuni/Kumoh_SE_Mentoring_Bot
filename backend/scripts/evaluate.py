from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
from shutil import copyfile
from tempfile import NamedTemporaryFile

from backend.app.config import REPOSITORY_ROOT, get_settings
from backend.app.evaluation import (
    EvaluationReport,
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


class RollbackFailure(RuntimeError):
    def __init__(
        self,
        failed_target_names: tuple[str, ...],
        failed_backup_paths: tuple[Path, ...],
        cause: OSError,
    ) -> None:
        self.failed_target_names = failed_target_names
        self.failed_backup_paths = failed_backup_paths
        target_names = ", ".join(failed_target_names)
        backup_paths = ", ".join(str(path) for path in failed_backup_paths)
        message = f"{target_names} 복구 실패"
        if backup_paths:
            message += f"; 보존된 백업: {backup_paths}"
        super().__init__(message)
        self.__cause__ = cause


def _cleanup_artifacts(
    paths: list[Path | None], preserve: set[Path] | None = None
) -> OSError | None:
    first_error: OSError | None = None
    preserve = preserve or set()
    for path in paths:
        if path is None:
            continue
        if path in preserve:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            if first_error is None:
                first_error = exc
    return first_error


def _stage_text(target: Path, content: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=str(target.parent),
            suffix=".tmp",
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
    except OSError as exc:
        cleanup_error = _cleanup_artifacts([temporary_path])
        if cleanup_error is not None:
            raise RuntimeError(
                f"평가 보고서 임시 파일 정리에 실패했습니다: {cleanup_error}"
            ) from exc
        raise
    if temporary_path is None:
        raise RuntimeError("평가 보고서 임시 파일을 만들지 못했습니다.")
    return temporary_path


def _atomic_write(target: Path, content: str) -> None:
    temporary_path = _stage_text(target, content)
    try:
        temporary_path.replace(target)
    except OSError as exc:
        cleanup_error = _cleanup_artifacts([temporary_path])
        if cleanup_error is not None:
            raise RuntimeError(
                f"평가 보고서 임시 파일 정리에 실패했습니다: {cleanup_error}"
            ) from exc
        raise


def _backup_target(target: Path) -> Path | None:
    if not target.exists():
        return None
    with NamedTemporaryFile(
        mode="wb",
        delete=False,
        dir=str(target.parent),
        suffix=".bak",
    ) as handle:
        backup_path = Path(handle.name)
    try:
        copyfile(target, backup_path)
    except OSError as exc:
        cleanup_error = _cleanup_artifacts([backup_path])
        if cleanup_error is not None:
            raise RuntimeError(
                f"평가 보고서 백업 파일 정리에 실패했습니다: {cleanup_error}"
            ) from exc
        raise
    return backup_path


def _rollback_reports(
    targets: tuple[Path, ...], backups: tuple[Path | None, ...]
) -> None:
    first_error: OSError | None = None
    failed_targets: list[str] = []
    failed_backup_paths: list[Path] = []
    for target, backup in zip(targets, backups, strict=True):
        try:
            if backup is None:
                target.unlink(missing_ok=True)
            else:
                backup.replace(target)
        except OSError as exc:
            failed_targets.append(target.name)
            if backup is not None:
                failed_backup_paths.append(backup)
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise RollbackFailure(
            tuple(failed_targets), tuple(failed_backup_paths), first_error
        ) from first_error


def write_reports(report: EvaluationReport, output_dir: Path) -> None:
    json_path = output_dir / "latest.json"
    markdown_path = output_dir / "latest.md"
    reports = (
        (json_path, report.model_dump_json(indent=2) + "\n"),
        (markdown_path, render_markdown(report)),
    )
    targets = tuple(target for target, _content in reports)
    staged: list[Path] = []
    backups: list[Path | None] = []
    commit_started = False

    try:
        staged.extend(_stage_text(target, content) for target, content in reports)
        backups.extend(_backup_target(target) for target in targets)
        commit_started = True
        for target, temporary_path in zip(targets, staged, strict=True):
            temporary_path.replace(target)
    except Exception as original_error:
        rollback_error: Exception | None = None
        preserved_backups: set[Path] = set()
        if commit_started:
            try:
                _rollback_reports(targets, tuple(backups))
            except RollbackFailure as exc:
                rollback_error = exc
                preserved_backups = set(exc.failed_backup_paths)
            except Exception as exc:
                rollback_error = exc
        cleanup_error = _cleanup_artifacts(
            [*staged, *backups], preserve=preserved_backups
        )
        if rollback_error is not None:
            message = f"평가 보고서 롤백에 실패했습니다: {rollback_error}"
            if cleanup_error is not None:
                message += f"; 임시 파일 정리 실패: {cleanup_error}"
            raise RuntimeError(message) from original_error
        if cleanup_error is not None:
            raise RuntimeError(
                f"평가 보고서 임시 파일 정리에 실패했습니다: {cleanup_error}"
            ) from original_error
        raise

    cleanup_error = _cleanup_artifacts([*staged, *backups])
    if cleanup_error is not None:
        raise RuntimeError(
            f"평가 보고서 임시 파일 정리에 실패했습니다: {cleanup_error}"
        ) from cleanup_error


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
    except (FileNotFoundError, OSError, ValueError, RuntimeError) as exc:
        print(f"평가 실행 오류: {exc}", file=sys.stderr)
        return 2

    print_summary(report)
    return 1 if report.summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
