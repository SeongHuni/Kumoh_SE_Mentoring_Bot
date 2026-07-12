# SE Mentor Bot Automated RAG Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic local End-to-End evaluation CLI that checks topic classification, grounded behavior, latest-source compliance, and expected source titles across at least 30 structured questions.

**Architecture:** Keep evaluation logic in a pure `backend/app/evaluation.py` module that receives a topic catalog, enriched posts, and an `ask` callable. Add a thin `backend/scripts/evaluate.py` wiring layer for settings, provider selection, Chroma, report persistence, console output, and exit codes. Generated reports stay outside Git while the structured baseline and progress evidence are committed.

**Tech Stack:** Python 3.11+, Pydantic 2, FastAPI domain models, ChromaDB, pytest, Ruff, JSON, Markdown

---

## Scope And File Map

| File | Responsibility |
| --- | --- |
| `backend/app/evaluation.py` | Input/result models, loader, case evaluation, metrics, Markdown rendering |
| `backend/scripts/evaluate.py` | CLI parsing, local/configured runtime wiring, atomic report writes, exit codes |
| `backend/tests/test_evaluation.py` | Pure evaluation model and behavior tests |
| `backend/tests/test_evaluate_script.py` | CLI orchestration and exit-code tests |
| `backend/tests/test_evaluation_dataset.py` | Committed 30-case baseline schema and distribution regression |
| `data/evaluation/questions.json` | Structured normative baseline |
| `data/evaluation/reports/` | Generated `latest.json` and `latest.md`; ignored by Git |
| `.gitignore` | Generated evaluation report exclusion |
| `README.md` | Quick evaluation command |
| `docs/rag/operations-evaluation.md` | Evaluation workflow and interpretation |
| `docs/PROJECT_STATUS.md` | P1-1 status and measured outcome |
| `docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md` | RED/GREEN/commit/next-step continuity |

Do not modify `/api/chat`, frontend response types, Chroma metadata schema, or crawler behavior in this plan.

## Execution Setup: Isolated Worktree And Baseline

- [ ] **Step 1: Invoke the worktree skill and verify both checkouts are clean**

Use `superpowers:using-git-worktrees`, then run:

```powershell
git -C C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot status --short --branch
git -C C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot\.worktrees\topic-latest status --short --branch
```

Expected: both commands show no modified or untracked files.

- [ ] **Step 2: Reuse the isolated worktree and create the evaluation branch from main**

```powershell
Set-Location C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot\.worktrees\topic-latest
git switch -c codex/rag-evaluation main
git status --short --branch
```

Expected: current branch is `codex/rag-evaluation` and the worktree is clean. The existing `codex/topic-latest` branch remains unchanged and available in the main checkout.

- [ ] **Step 3: Verify or install isolated dependencies**

```powershell
Test-Path backend/.venv/Scripts/python.exe
Test-Path frontend/node_modules/.bin/vitest.cmd
```

Expected: both print `True`. If Python is missing, run:

```powershell
py -3.13 -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
```

If frontend dependencies are missing, run:

```powershell
npm --prefix frontend ci --ignore-scripts
```

- [ ] **Step 4: Run the pre-change baseline**

```powershell
backend/.venv/Scripts/python -m pytest backend/tests -q
backend/.venv/Scripts/python -m ruff check backend
npm --prefix frontend run test -- --run
```

Expected: 26 backend tests and 9 frontend tests pass; Ruff prints `All checks passed!`.

## Task 1: Evaluation Case Schema And Loader

**Files:**
- Create: `backend/app/evaluation.py`
- Create: `backend/tests/test_evaluation.py`
- Modify: `docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md`

- [ ] **Step 1: Write failing loader tests**

Create `backend/tests/test_evaluation.py` with these initial tests:

```python
import json

import pytest

from backend.app.evaluation import EvaluationCase, load_evaluation_cases


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


@pytest.mark.parametrize("case_id", ["Upper-Case", "space id", "한글-id", ""])
def test_case_requires_kebab_case_id(case_id: str) -> None:
    payload = valid_case(case_id)

    with pytest.raises(ValueError):
        EvaluationCase.model_validate(payload)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_evaluation.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'backend.app.evaluation'`.

- [ ] **Step 3: Implement the minimal input model and loader**

Create `backend/app/evaluation.py` with:

```python
from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

CASE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class EvaluationCase(BaseModel):
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
    def reject_contradictory_source_expectation(self) -> "EvaluationCase":
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
```

- [ ] **Step 4: Verify GREEN and Ruff**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_evaluation.py -q
backend/.venv/Scripts/python -m ruff check backend/app/evaluation.py backend/tests/test_evaluation.py
```

Expected: 7 tests pass and Ruff prints `All checks passed!`.

- [ ] **Step 5: Record progress and commit**

Append to the handoff:

```markdown
### Task 1 — EvaluationCase와 loader

- RED: evaluation module 부재로 test collection 실패
- GREEN: 유효 입력, 중복 id, kebab-case, grounded/source 모순 테스트 통과
- 다음 시작점: topic·grounded·latest source 평가 실패 테스트
```

Commit:

```bash
git add backend/app/evaluation.py backend/tests/test_evaluation.py docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md
git commit -m "feat: validate rag evaluation cases"
```

## Task 2: Pure Evaluation Engine And Reports

**Files:**
- Modify: `backend/app/evaluation.py`
- Modify: `backend/tests/test_evaluation.py`
- Modify: `docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md`

- [ ] **Step 1: Add failing evaluator tests**

Add these imports and helpers to `backend/tests/test_evaluation.py`:

```python
from datetime import UTC, datetime

from backend.app.domain import AnswerSource, BoardPost
from backend.app.evaluation import (
    EvaluationChecks,
    EvaluationMetric,
    EvaluationResult,
    build_evaluation_report,
    evaluate_cases,
    render_markdown,
)
from backend.app.schemas import ChatResponse
from backend.app.topic_rules import TopicCatalog, TopicRule


def catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("course_openings", "개설강좌", ("개설강좌",), ()),
            TopicRule("general", "전체 공지", (), ()),
        ),
    )


def post(post_id: str, topic_key: str, latest: bool) -> BoardPost:
    return BoardPost(
        id=post_id,
        source="kumoh",
        title=f"{post_id} 수강신청 안내",
        content="개설강좌 조회 안내",
        url=f"https://example.com/{post_id}",
        published_at="2026-03-20" if latest else "2026-03-10",
        crawled_at=datetime(2026, 3, 20 if latest else 10, tzinfo=UTC),
        topic_key=topic_key,
        topic_label="개설강좌" if topic_key == "course_openings" else "전체 공지",
        is_latest_topic=latest,
    )


def response(*, grounded: bool, url: str | None = None, title: str = "") -> ChatResponse:
    sources = []
    if url is not None:
        sources.append(
            AnswerSource(
                title=title,
                url=url,
                source="kumoh",
                published_at="2026-03-20",
                score=0.9,
            )
        )
    return ChatResponse(answer="답변", sources=sources, grounded=grounded)
```

Add behavior tests:

```python
def test_evaluate_cases_passes_matching_latest_source() -> None:
    case = EvaluationCase.model_validate(valid_case())
    posts = [
        post("old", "course_openings", False),
        post("new", "course_openings", True),
    ]

    results = evaluate_cases(
        [case],
        catalog=catalog(),
        posts=posts,
        ask=lambda question: response(
            grounded=True,
            url="https://example.com/new",
            title="new 수강신청 안내",
        ),
    )

    assert results[0].passed is True
    assert results[0].checks == EvaluationChecks(
        topic_match=True,
        grounded_match=True,
        latest_only_match=True,
        source_title_match=True,
    )
    assert results[0].failures == []


def test_evaluate_cases_reports_grounded_stale_and_title_failures() -> None:
    case = EvaluationCase.model_validate(valid_case())
    posts = [
        post("old", "course_openings", False),
        post("new", "course_openings", True),
    ]

    results = evaluate_cases(
        [case],
        catalog=catalog(),
        posts=posts,
        ask=lambda question: response(
            grounded=False,
            url="https://example.com/old",
            title="old 공지",
        ),
    )

    assert results[0].passed is False
    assert results[0].checks.grounded_match is False
    assert results[0].checks.latest_only_match is False
    assert results[0].checks.source_title_match is False
    assert any("grounded" in failure for failure in results[0].failures)
    assert any("최신" in failure for failure in results[0].failures)


def test_evaluate_cases_reports_topic_mismatch() -> None:
    case = EvaluationCase.model_validate(valid_case())

    results = evaluate_cases(
        [case],
        catalog=catalog(),
        posts=[post("new", "course_openings", True)],
        ask=lambda question: response(
            grounded=True,
            url="https://example.com/new",
            title="new 수강신청 안내",
        ),
    )

    assert results[0].actual_topic_key == "course_openings"
    assert results[0].checks.topic_match is True

    mismatch_payload = valid_case("forced-topic-mismatch")
    mismatch_payload["question"] = "학과 소식을 알려줘"
    mismatch_results = evaluate_cases(
        [EvaluationCase.model_validate(mismatch_payload)],
        catalog=catalog(),
        posts=[post("new", "course_openings", True)],
        ask=lambda question: response(grounded=False),
    )

    assert mismatch_results[0].actual_topic_key == "general"
    assert mismatch_results[0].checks.topic_match is False
    assert any("topic 기대값 불일치" in item for item in mismatch_results[0].failures)


def test_evaluate_cases_rejects_unknown_expected_topic() -> None:
    payload = valid_case()
    payload["expected_topic_key"] = "missing"

    with pytest.raises(ValueError, match="존재하지 않는 topic"):
        evaluate_cases(
            [EvaluationCase.model_validate(payload)],
            catalog=catalog(),
            posts=[],
            ask=lambda question: response(grounded=False),
        )


def test_build_report_uses_only_applicable_checks_as_metric_denominator() -> None:
    result = EvaluationResult(
        case_id="general-no-answer",
        question="기숙사 식단을 알려줘",
        category="범위 밖",
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
        failures=[],
        passed=True,
    )

    report = build_evaluation_report(
        [result],
        provider="local",
        chat_model="local-answer",
        embedding_model="local-embedding",
        indexed_chunks=79,
        generated_at=datetime(2026, 7, 12, tzinfo=UTC),
    )

    assert report.summary.total == 1
    assert report.summary.passed == 1
    assert report.summary.source_title == EvaluationMetric(passed=0, total=0, rate=None)


def test_render_markdown_includes_summary_and_failure_reasons() -> None:
    result = EvaluationResult(
        case_id="failed-case",
        question="질문",
        category="테스트",
        expected_topic_key="general",
        actual_topic_key="general",
        expected_grounded=False,
        actual_grounded=True,
        sources=[],
        checks=EvaluationChecks(
            topic_match=True,
            grounded_match=False,
            latest_only_match=None,
            source_title_match=None,
        ),
        failures=["grounded 기대값 불일치"],
        passed=False,
    )
    report = build_evaluation_report(
        [result],
        provider="local",
        chat_model="local-answer",
        embedding_model="local-embedding",
        indexed_chunks=79,
        generated_at=datetime(2026, 7, 12, tzinfo=UTC),
    )

    markdown = render_markdown(report)

    assert "총 1건 · 통과 0건 · 실패 1건" in markdown
    assert "failed-case" in markdown
    assert "grounded 기대값 불일치" in markdown
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_evaluation.py -q
```

Expected: import fails because `EvaluationChecks`, `EvaluationResult`, `evaluate_cases`, `build_evaluation_report`, and `render_markdown` do not exist.

- [ ] **Step 3: Add result models and evaluator**

Append the following imports and models to `backend/app/evaluation.py`:

```python
from collections.abc import Callable
from datetime import UTC, datetime

from backend.app.domain import AnswerSource, BoardPost
from backend.app.schemas import ChatResponse
from backend.app.topic_rules import TopicCatalog


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
```

Append these functions:

```python
def _latest_urls(posts: list[BoardPost]) -> tuple[dict[str, set[str]], set[str]]:
    by_topic: dict[str, set[str]] = {}
    all_urls: set[str] = set()
    for post in posts:
        if not post.is_latest_topic:
            continue
        topic_key = post.topic_key or "general"
        by_topic.setdefault(topic_key, set()).add(post.url)
        all_urls.add(post.url)
    return by_topic, all_urls


def evaluate_cases(
    cases: list[EvaluationCase],
    *,
    catalog: TopicCatalog,
    posts: list[BoardPost],
    ask: Callable[[str], ChatResponse],
) -> list[EvaluationResult]:
    latest_by_topic, all_latest_urls = _latest_urls(posts)
    results: list[EvaluationResult] = []
    for case in cases:
        if catalog.rule_for(case.expected_topic_key) is None:
            raise ValueError(f"존재하지 않는 topic입니다: {case.expected_topic_key}")
        actual_topic = catalog.classify(case.question).key
        response = ask(case.question)
        failures: list[str] = []

        topic_match = actual_topic == case.expected_topic_key
        if not topic_match:
            failures.append(
                f"topic 기대값 불일치: expected={case.expected_topic_key}, actual={actual_topic}"
            )

        grounded_match = response.grounded == case.expected_grounded
        if response.grounded and not response.sources:
            grounded_match = False
            failures.append("grounded=true이지만 source가 없습니다.")
        elif not response.grounded and response.sources:
            grounded_match = False
            failures.append("grounded=false이지만 source가 있습니다.")
        elif not grounded_match:
            failures.append(
                f"grounded 기대값 불일치: expected={case.expected_grounded}, "
                f"actual={response.grounded}"
            )

        latest_only_match: bool | None = None
        if case.expected_latest_only:
            allowed_urls = (
                all_latest_urls
                if case.expected_topic_key == catalog.default_topic_key
                else latest_by_topic.get(case.expected_topic_key, set())
            )
            source_urls = {source.url for source in response.sources}
            latest_only_match = source_urls <= allowed_urls
            if case.expected_grounded and not source_urls:
                latest_only_match = False
            if not latest_only_match:
                failures.append("최신 주제 source가 아닌 URL이 포함됐습니다.")

        source_title_match: bool | None = None
        if case.expected_source_title_contains:
            titles = [source.title for source in response.sources]
            missing = [
                fragment
                for fragment in case.expected_source_title_contains
                if not any(fragment in title for title in titles)
            ]
            source_title_match = not missing
            if missing:
                failures.append(f"source 제목 기대값 누락: {', '.join(missing)}")

        checks = EvaluationChecks(
            topic_match=topic_match,
            grounded_match=grounded_match,
            latest_only_match=latest_only_match,
            source_title_match=source_title_match,
        )
        results.append(
            EvaluationResult(
                case_id=case.id,
                question=case.question,
                category=case.category,
                expected_topic_key=case.expected_topic_key,
                actual_topic_key=actual_topic,
                expected_grounded=case.expected_grounded,
                actual_grounded=response.grounded,
                sources=response.sources,
                checks=checks,
                failures=failures,
                passed=not failures,
            )
        )
    return results
```

- [ ] **Step 4: Add report aggregation and Markdown rendering**

Append:

```python
def _metric(values: list[bool | None]) -> EvaluationMetric:
    applicable = [value for value in values if value is not None]
    passed = sum(value is True for value in applicable)
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
    return EvaluationReport(
        generated_at=generated_at or datetime.now(UTC),
        provider=provider,
        chat_model=chat_model,
        embedding_model=embedding_model,
        indexed_chunks=indexed_chunks,
        summary=EvaluationSummary(
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            topic=_metric([result.checks.topic_match for result in results]),
            grounded=_metric([result.checks.grounded_match for result in results]),
            latest_only=_metric(
                [result.checks.latest_only_match for result in results]
            ),
            source_title=_metric(
                [result.checks.source_title_match for result in results]
            ),
        ),
        results=results,
    )


def _rate(metric: EvaluationMetric) -> str:
    return "N/A" if metric.rate is None else f"{metric.rate * 100:.1f}%"


def render_markdown(report: EvaluationReport) -> str:
    summary = report.summary
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- 생성 시각: {report.generated_at.isoformat()}",
        f"- Provider: {report.provider}",
        f"- Chat model: {report.chat_model}",
        f"- Embedding model: {report.embedding_model}",
        f"- Indexed chunks: {report.indexed_chunks}",
        f"- 총 {summary.total}건 · 통과 {summary.passed}건 · 실패 {summary.failed}건",
        "",
        "| Metric | Passed | Total | Rate |",
        "| --- | ---: | ---: | ---: |",
        f"| Topic | {summary.topic.passed} | {summary.topic.total} | {_rate(summary.topic)} |",
        f"| Grounded | {summary.grounded.passed} | {summary.grounded.total} | {_rate(summary.grounded)} |",
        f"| Latest-only | {summary.latest_only.passed} | {summary.latest_only.total} | {_rate(summary.latest_only)} |",
        f"| Source title | {summary.source_title.passed} | {summary.source_title.total} | {_rate(summary.source_title)} |",
        "",
        "## Cases",
        "",
    ]
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"### [{status}] {result.case_id}")
        lines.append("")
        lines.append(f"- 질문: {result.question}")
        lines.append(
            f"- Topic: expected={result.expected_topic_key}, actual={result.actual_topic_key}"
        )
        lines.append(
            f"- Grounded: expected={result.expected_grounded}, actual={result.actual_grounded}"
        )
        if result.sources:
            lines.append("- Sources:")
            lines.extend(
                f"  - {source.title} · {source.published_at or '날짜 없음'} · {source.url}"
                for source in result.sources
            )
        if result.failures:
            lines.append("- 실패 이유:")
            lines.extend(f"  - {failure}" for failure in result.failures)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 5: Verify GREEN and full backend regression**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_evaluation.py -q
backend/.venv/Scripts/python -m pytest backend/tests -q
backend/.venv/Scripts/python -m ruff check backend
```

Expected: evaluation tests and all existing backend tests pass; Ruff reports no errors.

- [ ] **Step 6: Record progress and commit**

Append this exact progress structure to the handoff, replacing the test count with pytest's printed count when it differs:

```markdown
### Task 2 — 순수 evaluator와 보고서

- RED: evaluator/result/report symbol import 실패
- GREEN: topic·grounded·latest-only·source-title·metric·Markdown 테스트 통과
- 전체 회귀: backend pytest와 Ruff 통과
- 다음 시작점: CLI 성공 0·평가 실패 1·실행 오류 2 테스트
```

Then commit:

```bash
git add backend/app/evaluation.py backend/tests/test_evaluation.py docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md
git commit -m "feat: evaluate rag quality expectations"
```

## Task 3: Evaluation CLI And Atomic Reports

**Files:**
- Create: `backend/scripts/evaluate.py`
- Create: `backend/tests/test_evaluate_script.py`
- Modify: `.gitignore`
- Modify: `docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md`

- [ ] **Step 1: Write failing CLI tests**

Create `backend/tests/test_evaluate_script.py`:

```python
from argparse import Namespace
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


def report(*, failed: int) -> EvaluationReport:
    result = EvaluationResult(
        case_id="case-1",
        question="질문",
        category="테스트",
        expected_topic_key="general",
        actual_topic_key="general",
        expected_grounded=False,
        actual_grounded=failed > 0,
        sources=[],
        checks=EvaluationChecks(
            topic_match=True,
            grounded_match=failed == 0,
            latest_only_match=True,
            source_title_match=None,
        ),
        failures=[] if failed == 0 else ["grounded 기대값 불일치"],
        passed=failed == 0,
    )
    metric = EvaluationMetric(passed=1 - failed, total=1, rate=float(1 - failed))
    return EvaluationReport(
        generated_at="2026-07-12T00:00:00Z",
        provider="local",
        chat_model="local-answer",
        embedding_model="local-embedding",
        indexed_chunks=79,
        summary=EvaluationSummary(
            total=1,
            passed=1 - failed,
            failed=failed,
            topic=EvaluationMetric(passed=1, total=1, rate=1.0),
            grounded=metric,
            latest_only=EvaluationMetric(passed=1, total=1, rate=1.0),
            source_title=EvaluationMetric(passed=0, total=0, rate=None),
        ),
        results=[result],
    )


def test_main_returns_zero_and_writes_reports_for_passing_evaluation(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(evaluate, "run_evaluation", lambda args: report(failed=0))

    exit_code = evaluate.main(["--output-dir", str(tmp_path), "--minimum-cases", "1"])

    assert exit_code == 0
    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "latest.md").exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_main_returns_one_after_writing_failed_evaluation_report(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(evaluate, "run_evaluation", lambda args: report(failed=1))

    exit_code = evaluate.main(["--output-dir", str(tmp_path), "--minimum-cases", "1"])

    assert exit_code == 1
    assert "grounded 기대값 불일치" in (tmp_path / "latest.md").read_text(
        encoding="utf-8"
    )


def test_main_returns_two_without_writing_reports_on_runtime_error(
    monkeypatch, tmp_path, capsys
) -> None:
    def fail(args: Namespace) -> EvaluationReport:
        raise ValueError("벡터 인덱스가 비어 있습니다.")

    monkeypatch.setattr(evaluate, "run_evaluation", fail)

    exit_code = evaluate.main(["--output-dir", str(tmp_path)])

    assert exit_code == 2
    assert not (tmp_path / "latest.json").exists()
    assert "벡터 인덱스가 비어 있습니다." in capsys.readouterr().err


def test_validate_minimum_cases_uses_full_dataset_count() -> None:
    with pytest.raises(ValueError, match="최소 30개"):
        evaluate.validate_minimum_cases(case_count=29, minimum=30)


def test_validate_indexed_chunks_rejects_empty_index() -> None:
    with pytest.raises(ValueError, match="벡터 인덱스가 비어"):
        evaluate.validate_indexed_chunks(0)
```

- [ ] **Step 2: Run CLI tests and verify RED**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_evaluate_script.py -q
```

Expected: import fails because `backend.scripts.evaluate` does not exist.

- [ ] **Step 3: Implement CLI parsing and runtime wiring**

Create `backend/scripts/evaluate.py` with these interfaces and behavior:

```python
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path
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
    parser = argparse.ArgumentParser(description="RAG 품질 평가를 실행합니다.")
    parser.add_argument(
        "--questions",
        type=Path,
        default=REPOSITORY_ROOT / "data/evaluation/questions.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "data/evaluation/reports",
    )
    parser.add_argument(
        "--provider",
        choices=("local", "configured"),
        default="local",
    )
    parser.add_argument("--minimum-cases", type=int, default=30)
    parser.add_argument("--limit", type=int)
    return parser.parse_args(argv)


def validate_minimum_cases(*, case_count: int, minimum: int) -> None:
    if minimum < 1:
        raise ValueError("minimum-cases는 1 이상이어야 합니다.")
    if case_count < minimum:
        raise ValueError(f"평가 질문은 최소 {minimum}개가 필요합니다: {case_count}개")


def validate_indexed_chunks(indexed_chunks: int) -> None:
    if indexed_chunks == 0:
        raise ValueError("벡터 인덱스가 비어 있습니다. 재인덱싱을 먼저 실행하세요.")


def run_evaluation(args: argparse.Namespace) -> EvaluationReport:
    settings = get_settings()
    if args.provider == "local":
        settings = replace(settings, ai_provider="local")
    cases = load_evaluation_cases(args.questions)
    validate_minimum_cases(case_count=len(cases), minimum=args.minimum_cases)
    if args.limit is not None and args.limit < 1:
        raise ValueError("limit은 1 이상이어야 합니다.")
    selected_cases = cases[: args.limit] if args.limit is not None else cases

    catalog = load_topic_catalog(settings.topic_rules_path)
    posts = enrich_posts(load_posts(settings.raw_posts_path), catalog)
    store = ChromaVectorStore(settings.chroma_path, settings.chroma_collection)
    indexed_chunks = store.count()
    validate_indexed_chunks(indexed_chunks)
    provider = create_provider(settings)
    service = RAGService(
        provider=provider,
        vector_store=store,
        top_k=settings.rag_top_k,
        min_score=settings.rag_min_score,
        topic_catalog=catalog,
        posts=posts,
    )
    results = evaluate_cases(
        selected_cases,
        catalog=catalog,
        posts=posts,
        ask=service.ask,
    )
    chat_model, embedding_model = effective_models(settings)
    return build_evaluation_report(
        results,
        provider=selected_provider_name(settings),
        chat_model=chat_model,
        embedding_model=embedding_model,
        indexed_chunks=indexed_chunks,
    )
```

- [ ] **Step 4: Implement atomic report writes and exit codes**

Append:

```python
def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        suffix=".tmp",
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def write_reports(report: EvaluationReport, output_dir: Path) -> None:
    _atomic_write(
        output_dir / "latest.json",
        report.model_dump_json(indent=2) + "\n",
    )
    _atomic_write(output_dir / "latest.md", render_markdown(report))


def print_summary(report: EvaluationReport) -> None:
    summary = report.summary
    print(
        f"평가 {summary.total}건: 통과 {summary.passed}건, 실패 {summary.failed}건 "
        f"(provider={report.provider}, chunks={report.indexed_chunks})"
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
```

- [ ] **Step 5: Ignore generated reports**

Add to `.gitignore`:

```gitignore
data/evaluation/reports/
```

- [ ] **Step 6: Verify GREEN, atomic outputs, and regression**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_evaluate_script.py -q
backend/.venv/Scripts/python -m pytest backend/tests -q
backend/.venv/Scripts/python -m ruff check backend
git check-ignore data/evaluation/reports/latest.json
```

Expected: all tests pass, Ruff passes, and `git check-ignore` prints the report path.

- [ ] **Step 7: Record progress and commit**

Append:

```markdown
### Task 3 — 평가 CLI와 원자적 보고서

- RED: backend.scripts.evaluate import 실패
- GREEN: 성공 0, 품질 실패 1, 실행 오류 2, 최소 케이스, 빈 인덱스 테스트 통과
- 보고서: latest.json·latest.md 원자적 저장, data/evaluation/reports Git ignore 확인
- 다음 시작점: committed dataset 30개·category 분포 실패 테스트
```

Commit:

```bash
git add .gitignore backend/scripts/evaluate.py backend/tests/test_evaluate_script.py docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md
git commit -m "feat: add rag evaluation cli"
```

## Task 4: Structured 30-Case Baseline

**Files:**
- Modify: `data/evaluation/questions.json`
- Create: `backend/tests/test_evaluation_dataset.py`
- Modify: `docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md`

- [ ] **Step 1: Write the failing committed-dataset test**

Create `backend/tests/test_evaluation_dataset.py`:

```python
from collections import Counter

from backend.app.config import REPOSITORY_ROOT
from backend.app.evaluation import load_evaluation_cases


def test_committed_evaluation_dataset_has_required_size_and_distribution() -> None:
    cases = load_evaluation_cases(REPOSITORY_ROOT / "data/evaluation/questions.json")
    counts = Counter(case.category for case in cases)

    assert len(cases) >= 30
    minimum_counts = {
        "개설강좌": 4,
        "수강신청": 5,
        "캡스톤": 4,
        "진로·취업": 4,
        "장학금": 4,
        "졸업요건": 3,
        "일반 공지": 3,
        "범위 밖": 3,
    }
    assert all(counts[category] >= minimum for category, minimum in minimum_counts.items())
    assert all(case.expected_latest_only for case in cases)
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_evaluation_dataset.py -q
```

Expected: existing 8-case file fails schema validation or `len(cases) >= 30`.

- [ ] **Step 3: Replace the dataset with 30 normative cases**

Replace `data/evaluation/questions.json` with cases using these exact IDs and expectations:

| ID | Question | Category | Topic | Grounded | Source fragments | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `course-openings-current` | 이번 학기 개설강좌를 알려줘 | 개설강좌 | course_openings | true | `["수강신청 안내"]` | 현재 저장 데이터의 최신 개설강좌 baseline |
| `course-openings-lookup` | 개설강좌 조회 방법은? | 개설강좌 | course_openings | true | `["수강신청 안내"]` | 최신 공지에 조회 경로가 있음 |
| `course-openings-available` | 수강 가능 과목은 어디서 확인해? | 개설강좌 | course_openings | true | `["수강신청 안내"]` | 개설강좌 조회 동의어 검증 |
| `course-openings-2026-first` | 2026학년도 1학기 개설 과목을 알려줘 | 개설강좌 | course_openings | false | `[]` | 현재 baseline은 2025학년도 2학기라 거절해야 함 |
| `registration-recent` | 최근 수강신청 일정과 유의사항을 알려줘 | 수강신청 | registration | false | `[]` | 최신 registration 글이 일반 수강신청 일정 공지가 아님 |
| `registration-change` | 수강신청 변경 방법을 알려줘 | 수강신청 | registration | false | `[]` | 최신 글에 수강 변경 근거가 없음 |
| `registration-early-employment` | 수강신청 후 여름계절수업 조기취업자 출석인정신청 안내를 찾아줘 | 수강신청 | registration | true | `["조기취업자 출석인정신청"]` | 최신 registration source 직접 조회 |
| `registration-period` | 수강 신청 기간은 언제야? | 수강신청 | registration | false | `[]` | 최신 글에 일반 수강신청 기간 근거가 없음 |
| `registration-course-change` | 최근 수강변경 공지를 알려줘 | 수강신청 | registration | false | `[]` | 최신 글에 수강변경 근거가 없음 |
| `capstone-plan` | 캡스톤디자인 운영 계획을 알려줘 | 캡스톤 | capstone | true | `["캡스톤 디자인 운영 계획"]` | 최신 캡스톤 운영계획 직접 조회 |
| `capstone-apply` | 캡스톤디자인 신청 방법이 뭐야? | 캡스톤 | capstone | true | `["캡스톤 디자인 운영 계획"]` | 운영계획 내 신청 안내 검증 |
| `capstone-schedule` | 캡스톤 디자인 일정은 언제야? | 캡스톤 | capstone | true | `["캡스톤 디자인 운영 계획"]` | 운영계획 내 일정 검증 |
| `capstone-second-semester` | 2026학년도 2학기 캡스톤디자인 공지를 알려줘 | 캡스톤 | capstone | false | `[]` | 현재 baseline은 1학기라 거절해야 함 |
| `career-faculty-lecture` | 진로 관련 전임교원 초빙 공개강의 심사 공고를 찾아줘 | 진로·취업 | career | true | `["전임교원 초빙 공개강의"]` | 현재 최신 career source 직접 조회 |
| `career-program` | 최근 취업 프로그램을 알려줘 | 진로·취업 | career | false | `[]` | 최신 career 글은 학생 취업 프로그램이 아님 |
| `career-internship` | 인턴 관련 공지가 있어? | 진로·취업 | career | false | `[]` | 최신 career 글에 인턴 근거가 없음 |
| `career-recruitment` | 최근 채용 공지를 찾아줘 | 진로·취업 | career | true | `["전임교원 초빙"]` | 최신 source의 채용 성격 검증 |
| `scholarship-bootcamp` | 장학 관련 방산AI인재양성부트캠프 설명회 공지를 찾아줘 | 장학금 | scholarship | true | `["방산AI인재양성부트캠프"]` | 현재 최신 scholarship source 직접 조회 |
| `scholarship-apply` | 장학금 신청 공지를 알려줘 | 장학금 | scholarship | false | `[]` | 최신 글에 장학금 신청 근거가 없음 |
| `scholarship-selection` | 장학생 선발 기준은? | 장학금 | scholarship | false | `[]` | 최신 글에 장학생 선발 기준이 없음 |
| `scholarship-recent` | 최근 장학 공지를 알려줘 | 장학금 | scholarship | false | `[]` | 현재 최신 글의 scholarship 분류 정확성 감사용 |
| `graduation-requirements` | 졸업요건을 확인해줘 | 졸업요건 | graduation | false | `[]` | graduation 분류 게시글이 없음 |
| `graduation-certification` | 졸업인증 기준은? | 졸업요건 | graduation | false | `[]` | 졸업인증 근거 데이터가 없음 |
| `graduation-credits` | 졸업 요건 이수학점을 알려줘 | 졸업요건 | graduation | false | `[]` | 졸업 이수학점 근거 데이터가 없음 |
| `general-ax-project` | AX 기반 역량 강화 프로젝트 공모 기간 연장 안내를 찾아줘 | 일반 공지 | general | true | `["AX 기반 역량 강화 프로젝트"]` | 최신 general source 직접 조회 |
| `general-recent-department` | 최근 학과 공지를 알려줘 | 일반 공지 | general | true | `[]` | 모든 주제 최신 글 대상 일반 검색 |
| `general-software-notice` | 소프트웨어전공 공지를 알려줘 | 일반 공지 | general | true | `[]` | default topic 일반 공지 검색 |
| `out-of-scope-cafeteria` | 오늘 학생식당 메뉴를 알려줘 | 범위 밖 | general | false | `[]` | 수집 범위 밖 식단 질문 |
| `out-of-scope-dormitory` | 데이터에 없는 기숙사 식단을 알려줘 | 범위 밖 | general | false | `[]` | 수집 범위 밖 기숙사 식단 질문 |
| `out-of-scope-weather` | 오늘 학교 날씨를 알려줘 | 범위 밖 | general | false | `[]` | 수집 범위 밖 실시간 날씨 질문 |

Each JSON object must copy the table's values exactly, include `expected_latest_only: true`, use the source-fragment JSON array shown in the table, and use the Notes text as `notes`.

- [ ] **Step 4: Verify dataset GREEN**

Run:

```powershell
backend/.venv/Scripts/python -m pytest backend/tests/test_evaluation_dataset.py -q
backend/.venv/Scripts/python -m pytest backend/tests -q
backend/.venv/Scripts/python -m ruff check backend
```

Expected: dataset regression and all backend tests pass.

- [ ] **Step 5: Reindex and run the real local evaluation**

Run:

```powershell
backend/.venv/Scripts/python -m backend.scripts.index --reset
backend/.venv/Scripts/python -m backend.scripts.evaluate
```

Expected:

- index command exits 0 and reports 46 posts, 79 chunks with local embedding;
- evaluate exits 0 when all normative expectations pass, or exits 1 with `latest.json` and `latest.md` listing genuine RAG quality gaps;
- exit 2 is a task failure that must be fixed before continuing.

Do not weaken an expectation solely to obtain exit 0. Record every exit-1 case in the handoff and `PROJECT_STATUS.md` as a follow-up RAG defect.

- [ ] **Step 6: Record progress and commit**

Append a `Task 4 — 30개 baseline` section to the handoff containing:

- the dataset test's printed case count and category counts;
- the exact evaluate process exit code;
- `report.summary.total`, `passed`, `failed`, and four metric objects copied from `latest.json`;
- every `case_id` whose `passed` is false;
- `다음 시작점: README·operations·PROJECT_STATUS에 측정 결과 반영`.

Commit:

```bash
git add data/evaluation/questions.json backend/tests/test_evaluation_dataset.py docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md
git commit -m "test: add structured rag evaluation baseline"
```

## Task 5: Operations Documentation And Status

**Files:**
- Modify: `README.md`
- Modify: `docs/rag/operations-evaluation.md`
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md`

- [ ] **Step 1: Add the quick-start command to README**

Add under `## 검증`:

```powershell
backend/.venv/Scripts/python -m backend.scripts.evaluate
```

Explain in two sentences that local is the default, reports are written to `data/evaluation/reports/`, exit 1 means measured quality failures, and exit 2 means execution/configuration failure.

Use these exact sentences:

```markdown
자동 평가는 외부 API 비용이 없는 local provider를 기본으로 사용하고 결과를 `data/evaluation/reports/latest.json`, `latest.md`에 저장합니다. 종료 코드 1은 측정된 품질 assertion 실패이며 보고서를 검토해야 한다는 뜻이고, 종료 코드 2는 입력·설정·인덱스 오류로 평가를 완료하지 못했다는 뜻입니다.
```

- [ ] **Step 2: Document the complete evaluation workflow**

Add to `docs/rag/operations-evaluation.md`:

````markdown
### 자동 평가

```powershell
backend/.venv/Scripts/python -m backend.scripts.index --reset
backend/.venv/Scripts/python -m backend.scripts.evaluate
```

- 기본 provider는 `local`이다.
- `--provider configured`는 현재 `.env` provider를 사용한다.
- `latest.json`, `latest.md`는 `data/evaluation/reports/`에 생성된다.
- exit 0은 전체 통과, exit 1은 품질 assertion 실패, exit 2는 실행 오류다.
- 데이터 재수집 후 30개 baseline 기대값을 공식 원문과 재검토한다.
````

Add this argument table immediately after the workflow:

```markdown
| 인자 | 기본값 | 용도 |
| --- | --- | --- |
| `--questions` | `data/evaluation/questions.json` | 평가 입력 파일 |
| `--output-dir` | `data/evaluation/reports` | JSON·Markdown 보고서 위치 |
| `--provider` | `local` | `local` 또는 현재 환경의 `configured` provider 선택 |
| `--minimum-cases` | `30` | 전체 입력 파일의 최소 케이스 수 |
| `--limit` | 없음 | schema·최소 수 검증 후 첫 N개만 smoke 실행 |
```

- [ ] **Step 3: Update project status using measured results**

In `docs/PROJECT_STATUS.md`:

- mark P1-1 `완료` when CLI and report generation work;
- record case count and actual topic/grounded/latest/source-title metrics;
- list genuine failed case IDs under active quality gaps when exit 1 occurred;
- set the next recommended task to P0-2 data refresh if failures are data-staleness related, otherwise to a focused RAG defect plan;
- retain the distinction between tool completion and RAG quality completion.

- [ ] **Step 4: Finalize handoff implementation state**

Record all commits, exact verification commands, actual report paths, known failures, and next task. The handoff must let a new worker resume without reading terminal history.

- [ ] **Step 5: Validate and commit docs**

Run:

```powershell
git diff --check
```

Expected: exit 0.

Commit:

```bash
git add README.md docs/rag/operations-evaluation.md docs/PROJECT_STATUS.md docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md
git commit -m "docs: document automated rag evaluation"
```

## Task 6: Full Verification And Final Review

**Files:**
- Verify: `backend/`
- Verify: `frontend/`
- Verify: `data/evaluation/questions.json`
- Verify: `docs/PROJECT_STATUS.md`

- [ ] **Step 1: Run full backend verification**

```powershell
backend/.venv/Scripts/python -m pytest backend/tests -q
backend/.venv/Scripts/python -m ruff check backend
```

Expected: all backend tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 2: Run frontend regression**

```powershell
npm --prefix frontend run test -- --run
frontend/node_modules/.bin/tsc.cmd -p frontend/tsconfig.json --noEmit --incremental false
npm --prefix frontend run lint
npm --prefix frontend run build
```

Expected: 9 existing frontend tests pass, TypeScript and ESLint exit 0, Next.js generates 4 static pages.

Restore the repository version of `frontend/next-env.d.ts` with `apply_patch` if Next.js rewrites only that generated convention file; do not commit the generated rewrite.

- [ ] **Step 3: Run the real evaluation and inspect reports**

```powershell
backend/.venv/Scripts/python -m backend.scripts.evaluate
Get-Content data/evaluation/reports/latest.md -Tail 200
```

Expected: exit 0 or documented quality exit 1; never exit 2. Confirm no API key, full post body, or environment dump appears in either report.

- [ ] **Step 4: Verify repository hygiene**

```powershell
git diff --check
git status --short --branch
git check-ignore data/evaluation/reports/latest.json
git check-ignore data/evaluation/reports/latest.md
```

Expected: no whitespace errors, only intentional changes before the final commit, and both generated reports are ignored.

- [ ] **Step 5: Review requirements line by line**

Check the design completion conditions against the implementation:

- 30+ structured cases
- local default
- four check types
- JSON and Markdown outputs
- exit 0/1/2 distinction
- atomic replacement
- no sensitive report content
- no runtime API change
- current progress and next work documented

Record any gap in the handoff before claiming completion.

- [ ] **Step 6: Commit any final documentation-only corrections**

If review changes documentation, commit only those files:

```bash
git add docs/PROJECT_STATUS.md docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md
git commit -m "docs: finalize rag evaluation handoff"
```

If no final corrections exist, do not create an empty commit.

## Plan Self-Review

- Spec sections 4–12 map to Tasks 1–5; completion verification maps to Task 6.
- Input and output type names stay consistent: `EvaluationCase`, `EvaluationChecks`, `EvaluationResult`, `EvaluationMetric`, `EvaluationSummary`, `EvaluationReport`.
- `evaluate_cases` is the only case execution function; `build_evaluation_report` is the only aggregation entry point.
- CLI default is always local and `configured` is explicit.
- Minimum case validation uses the full file before `--limit` is applied.
- Generated reports are written atomically and ignored by Git.
- Evaluation exit 1 is documented as a quality result, not an implementation crash.
- No task modifies chat API or frontend behavior.
- Every production behavior begins with a failing test and includes an exact verification command.
- Each implementation task updates the handoff before commit.
