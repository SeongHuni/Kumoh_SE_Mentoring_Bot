from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.domain import AnswerSource, BoardPost
from backend.app.schemas import ChatResponse
from backend.app.topic_rules import TopicCatalog

CASE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    question: str = Field(min_length=2, max_length=500)
    category: str
    expected_topic_key: str
    expected_grounded: bool
    expected_latest_only: bool
    expected_source_title_contains: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator(
        "id",
        "question",
        "category",
        "expected_topic_key",
        "notes",
        mode="before",
    )
    @classmethod
    def strip_strings(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not CASE_ID_PATTERN.fullmatch(value):
            raise ValueError("평가 id는 kebab-case여야 합니다.")
        return value

    @field_validator("category", "expected_topic_key")
    @classmethod
    def reject_blank_required_strings(cls, value: str) -> str:
        if not value:
            raise ValueError("필수 문자열은 비어 있을 수 없습니다.")
        return value

    @field_validator("expected_source_title_contains")
    @classmethod
    def normalize_title_fragments(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("source 제목 기대값은 비어 있을 수 없습니다.")
        return normalized

    @model_validator(mode="after")
    def reject_contradictory_source_expectation(self) -> EvaluationCase:
        if not self.expected_grounded and self.expected_source_title_contains:
            raise ValueError("grounded=false에는 source 제목 기대값을 둘 수 없습니다.")
        return self


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    if not path.exists():
        raise FileNotFoundError(f"평가 질문 파일이 없습니다: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("평가 질문은 비어 있지 않은 JSON 배열이어야 합니다.")
    cases = [EvaluationCase.model_validate(item) for item in payload]
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("중복 평가 id가 있습니다.")
    return cases


class EvaluationChecks(BaseModel):
    topic_match: bool
    grounded_match: bool
    latest_only_match: bool | None
    source_title_match: bool | None


class EvaluationResult(BaseModel):
    case_id: str
    question: str
    category: str
    expected_topic_key: str
    actual_topic_key: str
    expected_grounded: bool
    actual_grounded: bool
    sources: list[AnswerSource]
    checks: EvaluationChecks
    failures: list[str]
    passed: bool


class EvaluationMetric(BaseModel):
    passed: int
    total: int
    rate: float | None


class EvaluationSummary(BaseModel):
    total: int
    passed: int
    failed: int
    topic: EvaluationMetric
    grounded: EvaluationMetric
    latest_only: EvaluationMetric
    source_title: EvaluationMetric


class EvaluationReport(BaseModel):
    generated_at: datetime
    provider: str
    chat_model: str
    embedding_model: str
    indexed_chunks: int
    summary: EvaluationSummary
    results: list[EvaluationResult]


def _latest_urls(posts: Iterable[BoardPost]) -> tuple[dict[str, set[str]], set[str]]:
    by_topic: dict[str, set[str]] = {}
    all_latest: set[str] = set()
    for post in posts:
        if not post.is_latest_topic:
            continue
        topic_key = post.topic_key or "general"
        by_topic.setdefault(topic_key, set()).add(post.url)
        all_latest.add(post.url)
    return by_topic, all_latest


def evaluate_cases(
    cases: Iterable[EvaluationCase],
    *,
    catalog: TopicCatalog,
    posts: Iterable[BoardPost],
    ask: Callable[[str], ChatResponse],
) -> list[EvaluationResult]:
    latest_by_topic, all_latest_urls = _latest_urls(posts)
    results: list[EvaluationResult] = []

    for case in cases:
        if catalog.rule_for(case.expected_topic_key) is None:
            raise ValueError(f"존재하지 않는 topic입니다: {case.expected_topic_key}")

        actual_topic_key = catalog.classify(case.question).key
        actual = ask(case.question)
        failures: list[str] = []

        topic_match = case.expected_topic_key == actual_topic_key
        if not topic_match:
            failures.append(
                "topic 기대값 불일치: "
                f"expected={case.expected_topic_key}, actual={actual_topic_key}"
            )

        grounded_match = case.expected_grounded == actual.grounded
        if actual.grounded and not actual.sources:
            grounded_match = False
            failures.append("grounded=true이지만 source가 없습니다.")
        elif not actual.grounded and actual.sources:
            grounded_match = False
            failures.append("grounded=false이지만 source가 있습니다.")
        elif not grounded_match:
            failures.append(
                "grounded 기대값 불일치: "
                f"expected={case.expected_grounded}, actual={actual.grounded}"
            )

        latest_only_match: bool | None = None
        if case.expected_latest_only:
            allowed_urls = (
                all_latest_urls
                if case.expected_topic_key == catalog.default_topic_key
                else latest_by_topic.get(case.expected_topic_key, set())
            )
            source_urls = [source.url for source in actual.sources]
            latest_only_match = all(url in allowed_urls for url in source_urls)
            if case.expected_grounded and not source_urls:
                latest_only_match = False
            if not latest_only_match:
                failures.append("최신 주제 source가 아닌 URL이 포함됐습니다.")

        source_title_match: bool | None = None
        if case.expected_source_title_contains:
            missing_fragments = [
                fragment
                for fragment in case.expected_source_title_contains
                if not any(fragment in source.title for source in actual.sources)
            ]
            source_title_match = not missing_fragments
            if missing_fragments:
                failures.append(
                    "source 제목 기대값 누락: " + ", ".join(missing_fragments)
                )

        results.append(
            EvaluationResult(
                case_id=case.id,
                question=case.question,
                category=case.category,
                expected_topic_key=case.expected_topic_key,
                actual_topic_key=actual_topic_key,
                expected_grounded=case.expected_grounded,
                actual_grounded=actual.grounded,
                sources=actual.sources,
                checks=EvaluationChecks(
                    topic_match=topic_match,
                    grounded_match=grounded_match,
                    latest_only_match=latest_only_match,
                    source_title_match=source_title_match,
                ),
                failures=failures,
                passed=not failures,
            )
        )

    return results


def _metric(values: Iterable[bool | None]) -> EvaluationMetric:
    applicable = [value for value in values if value is not None]
    passed = sum(applicable)
    total = len(applicable)
    return EvaluationMetric(
        passed=passed,
        total=total,
        rate=round(passed / total, 4) if total else None,
    )


def build_evaluation_report(
    results: list[EvaluationResult],
    *,
    provider: str,
    chat_model: str,
    embedding_model: str,
    indexed_chunks: int,
    generated_at: datetime | None = None,
) -> EvaluationReport:
    passed = sum(result.passed for result in results)
    total = len(results)
    summary = EvaluationSummary(
        total=total,
        passed=passed,
        failed=total - passed,
        topic=_metric(result.checks.topic_match for result in results),
        grounded=_metric(result.checks.grounded_match for result in results),
        latest_only=_metric(result.checks.latest_only_match for result in results),
        source_title=_metric(result.checks.source_title_match for result in results),
    )
    return EvaluationReport(
        generated_at=generated_at or datetime.now(UTC),
        provider=provider,
        chat_model=chat_model,
        embedding_model=embedding_model,
        indexed_chunks=indexed_chunks,
        summary=summary,
        results=results,
    )


def render_markdown(report: EvaluationReport) -> str:
    def format_rate(metric: EvaluationMetric) -> str:
        return "N/A" if metric.rate is None else f"{metric.rate * 100:.1f}%"

    summary = report.summary
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- Generated at: {report.generated_at.isoformat()}",
        f"- Provider: {report.provider}",
        f"- Chat model: {report.chat_model}",
        f"- Embedding model: {report.embedding_model}",
        f"- Indexed chunks: {report.indexed_chunks}",
        "",
        "## Summary",
        "",
        f"총 {summary.total}건 · 통과 {summary.passed}건 · 실패 {summary.failed}건",
        "",
        "| Metric | Passed | Total | Rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, metric in (
        ("Topic", summary.topic),
        ("Grounded", summary.grounded),
        ("Latest-only", summary.latest_only),
        ("Source title", summary.source_title),
    ):
        lines.append(
            f"| {label} | {metric.passed} | {metric.total} | {format_rate(metric)} |"
        )

    lines.extend(["", "## Cases"])
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        lines.extend(
            [
                "",
                f"### [{status}] {result.case_id}",
                "",
                f"- Question: {result.question}",
                "- Topic: "
                f"expected={result.expected_topic_key}, actual={result.actual_topic_key}",
                "- Grounded: "
                f"expected={str(result.expected_grounded).lower()}, "
                f"actual={str(result.actual_grounded).lower()}",
                "",
                "#### Sources",
                "",
            ]
        )
        if result.sources:
            for source in result.sources:
                published_at = source.published_at or "날짜 없음"
                lines.append(f"- {source.title} · {published_at} · {source.url}")
        else:
            lines.append("- 없음")

        lines.extend(["", "#### Failures", ""])
        if result.failures:
            lines.extend(f"- {failure}" for failure in result.failures)
        else:
            lines.append("- 없음")

    return "\n".join(lines).rstrip() + "\n"
