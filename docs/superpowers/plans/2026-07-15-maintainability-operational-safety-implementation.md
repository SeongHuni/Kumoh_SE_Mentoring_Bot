# Maintainability And Operational Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the maintained documentation with the running RAG system and add fail-closed CLI, frontend HTTP, dependency, and container-operability safeguards without changing SE-board crawler internals.

**Architecture:** Preserve the existing FastAPI/Next.js boundaries and add small validation seams at the four unsafe edges: crawler invocation, evaluation/index compatibility, browser HTTP requests, and container process checks. Keep volatile facts in `docs/PROJECT_STATUS.md`, keep historical records immutable, and finish every behavior change with focused tests plus the existing full quality gates.

**Tech Stack:** Python 3.12/3.13, FastAPI, Pydantic, ChromaDB, pytest, Ruff, Next.js 15, React 19, TypeScript, Vitest, Testing Library, Docker Compose, Markdown.

---

## Working assumptions

- Run every command from the repository root of the `codex/maintainability-audit` worktree.
- Use `backend/.venv/Scripts/python.exe` on Windows. The equivalent Linux executable is `backend/.venv/bin/python`.
- Do not edit `backend/app/crawling/seboard.py` or generate SE-board data.
- Do not edit dated files under `docs/superpowers/specs`, `plans`, or old `handoffs` after they are committed.
- Current verified baseline: backend 154 tests at 91.42% coverage; frontend 9 tests, typecheck, lint, and build pass.
- Docker is not installed on the current host. Static deployment tests are required; runtime container checks remain explicitly unverified unless another host runs them.

## File responsibility map

| File | Responsibility after this change |
|---|---|
| `backend/scripts/crawl.py` | Fail-closed collection entry point; SE collection defaults off and requires explicit permission acknowledgement |
| `backend/scripts/evaluate.py` | Refuses an index whose manifest does not match the selected evaluation provider/settings |
| `backend/scripts/audit_data.py` | Uses application-configured data paths unless CLI paths override them |
| `backend/app/main.py` | Exposes process liveness separately from RAG readiness |
| `backend/app/schemas.py` | Owns the typed liveness response contract |
| `frontend/app/lib/chatApi.ts` | Owns chat HTTP, timeout, parsing, and user-facing transport errors |
| `frontend/app/page.tsx` | Owns form and message state, not transport details |
| `compose.yaml` | Owns build-time frontend URL wiring and process health ordering |
| `frontend/package.json` / `package-lock.json` | Own a reproducible, non-vulnerable test toolchain |
| `README.md` | Shortest supported setup/run/verification path |
| `docs/PROJECT_STATUS.md` | Only canonical owner of volatile counts, readiness, risks, and remaining verification |
| `docs/RAG_ARCHITECTURE.md` | Documentation precedence and stable RAG invariants |
| `docs/rag/operations-evaluation.md` | Authoritative operational commands |
| `AGENTS.md` | Current contributor conventions; delegates operational detail to canonical docs |

## Task 1: Make SE collection opt-in and fail closed

**Files:**
- Modify: `backend/tests/test_crawl_script.py`
- Modify: `backend/scripts/crawl.py`

- [ ] **Step 1: Add failing default and permission-boundary tests**

Add these tests to `backend/tests/test_crawl_script.py`:

```python
def test_parse_args_disables_seboard_by_default() -> None:
    args = crawl.parse_args([])

    assert args.seboard_limit == 0
    assert args.seboard_permission_confirmed is False


def test_seboard_limit_requires_permission_before_crawler_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    app_settings = settings(tmp_path)
    constructor_calls: list[str] = []

    class UnexpectedSeBoard:
        def __init__(self, **_kwargs) -> None:
            constructor_calls.append("created")

        def crawl(self, _limit: int) -> list[BoardPost]:
            return []

    monkeypatch.setattr(crawl, "get_settings", lambda: app_settings)
    monkeypatch.setattr(crawl, "SeBoardCrawler", UnexpectedSeBoard)

    exit_code = crawl.main(
        ["--kumoh-limit", "0", "--seboard-limit", "1"]
    )

    assert exit_code == 2
    assert constructor_calls == []
    assert "서면 허가" in capsys.readouterr().err
```

In `test_allow_partial_writes_candidate_without_overwriting_raw_posts`, add the acknowledgement immediately after the positive SE limit so the existing partial-failure scenario remains intentional:

```python
            "--seboard-limit",
            "1",
            "--seboard-permission-confirmed",
            "--allow-partial",
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_crawl_script.py -q
```

Expected: failure because the current default is 50 and `Namespace` has no `seboard_permission_confirmed` field.

- [ ] **Step 3: Implement the minimal CLI guard**

Change the SE arguments in `backend/scripts/crawl.py` to:

```python
    parser.add_argument(
        "--seboard-limit",
        type=int,
        default=0,
        help="승인된 SE 소스 수집 건수; 기본값은 비활성",
    )
    parser.add_argument(
        "--seboard-permission-confirmed",
        action="store_true",
        help="운영자 서면 허가 또는 승인된 공식 API 확보를 명시적으로 확인",
    )
```

Immediately after `settings = get_settings()` add:

```python
    if args.seboard_limit > 0 and not args.seboard_permission_confirmed:
        print(
            "오류 - SE 게시판 수집에는 운영자 서면 허가 또는 승인된 공식 API 확인이 필요합니다.",
            file=sys.stderr,
        )
        return 2
```

Do not alter the `SeBoardCrawler` class or its API/Selenium behavior.

- [ ] **Step 4: Run focused and related tests and verify GREEN**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_crawl_script.py backend/tests/test_kumoh_crawler.py -q
backend/.venv/Scripts/python.exe -m ruff check backend/scripts/crawl.py backend/tests/test_crawl_script.py
```

Expected: all selected tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 5: Commit the crawler boundary**

```bash
git add backend/scripts/crawl.py backend/tests/test_crawl_script.py
git commit -m "fix: disable unapproved seboard collection"
```

## Task 2: Validate evaluation/index compatibility before provider use

**Files:**
- Modify: `backend/tests/test_evaluate_script.py`
- Modify: `backend/scripts/evaluate.py`

- [ ] **Step 1: Add an incompatible-index regression test**

Add these imports to `backend/tests/test_evaluate_script.py`:

```python
from dataclasses import replace
from unittest.mock import Mock

from backend.app.index_manifest import IndexCompatibility
```

Add the following helper and test after the existing `report` helper:

```python
def evaluation_args(tmp_path: Path, provider: str = "local") -> Namespace:
    return Namespace(
        questions=tmp_path / "questions.json",
        output_dir=tmp_path / "reports",
        provider=provider,
        minimum_cases=1,
        limit=1,
    )


def stub_evaluation_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[object, object]:
    app_settings = replace(
        evaluate.get_settings(),
        ai_provider="local",
        openai_api_key=None,
        chroma_path=tmp_path / "chroma",
        raw_posts_path=tmp_path / "posts.json",
        topic_rules_path=tmp_path / "topics.json",
    )
    store = object()
    catalog = object()
    monkeypatch.setattr(evaluate, "get_settings", lambda: app_settings)
    monkeypatch.setattr(evaluate, "load_evaluation_cases", lambda _path: [object()])
    monkeypatch.setattr(evaluate, "load_topic_catalog", lambda _path: catalog)
    monkeypatch.setattr(evaluate, "load_posts", lambda _path: [])
    monkeypatch.setattr(evaluate, "enrich_posts", lambda posts, _catalog: posts)
    monkeypatch.setattr(evaluate, "ChromaVectorStore", lambda *_args: store)
    return app_settings, store


def test_run_evaluation_blocks_incompatible_index_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_settings, store = stub_evaluation_inputs(monkeypatch, tmp_path)
    compatibility_check = Mock(
        return_value=IndexCompatibility(
            compatible=False,
            reason="settings_mismatch",
            indexed_chunks=84,
        )
    )
    provider_factory = Mock()
    monkeypatch.setattr(evaluate, "assess_index_compatibility", compatibility_check)
    monkeypatch.setattr(evaluate, "create_provider", provider_factory)

    with pytest.raises(ValueError, match="settings_mismatch"):
        evaluate.run_evaluation(evaluation_args(tmp_path))

    compatibility_check.assert_called_once_with(settings=app_settings, store=store)
    provider_factory.assert_not_called()
```

- [ ] **Step 2: Run the incompatible-index test and verify RED**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_evaluate_script.py::test_run_evaluation_blocks_incompatible_index_before_provider -q
```

Expected: failure because `backend.scripts.evaluate` does not import or call `assess_index_compatibility`.

- [ ] **Step 3: Replace count-only validation with strict manifest validation**

Add the import in `backend/scripts/evaluate.py`:

```python
from backend.app.index_manifest import assess_index_compatibility
```

Delete the now-redundant `validate_indexed_chunks` function. Replace:

```python
    indexed_chunks = vector_store.count()
    validate_indexed_chunks(indexed_chunks)
```

with:

```python
    compatibility = assess_index_compatibility(
        settings=effective_settings,
        store=vector_store,
    )
    if not compatibility.compatible:
        raise ValueError(
            "현재 평가 provider·설정·데이터와 인덱스가 호환되지 않습니다 "
            f"({compatibility.reason}). 같은 provider로 index --reset을 실행하세요."
        )
    indexed_chunks = compatibility.indexed_chunks
```

Remove `test_validate_indexed_chunks_rejects_empty_store`, because empty indexes now use the same strict compatibility path as the API.

- [ ] **Step 4: Add a compatible-index count propagation test**

Append:

```python
def test_run_evaluation_uses_compatible_manifest_chunk_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_settings, store = stub_evaluation_inputs(monkeypatch, tmp_path)
    compatibility_check = Mock(
        return_value=IndexCompatibility(
            compatible=True,
            reason="compatible",
            indexed_chunks=84,
            fingerprint="a" * 64,
            generation="2026-07-15T00:00:00+00:00",
        )
    )
    expected_report = report(failed=0)
    report_builder = Mock(return_value=expected_report)
    provider = object()
    service = Mock()
    monkeypatch.setattr(evaluate, "assess_index_compatibility", compatibility_check)
    monkeypatch.setattr(evaluate, "create_provider", Mock(return_value=provider))
    monkeypatch.setattr(evaluate, "RAGService", Mock(return_value=service))
    monkeypatch.setattr(evaluate, "evaluate_cases", Mock(return_value=[]))
    monkeypatch.setattr(evaluate, "build_evaluation_report", report_builder)

    result = evaluate.run_evaluation(evaluation_args(tmp_path))

    assert result is expected_report
    compatibility_check.assert_called_once_with(settings=app_settings, store=store)
    assert report_builder.call_args.kwargs["indexed_chunks"] == 84
```

- [ ] **Step 5: Run focused tests and Ruff and verify GREEN**

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_evaluate_script.py backend/tests/test_index_manifest.py -q
backend/.venv/Scripts/python.exe -m ruff check backend/scripts/evaluate.py backend/tests/test_evaluate_script.py
```

Expected: all selected tests pass; mismatch tests stop before `create_provider`.

- [ ] **Step 6: Commit evaluation safety**

```bash
git add backend/scripts/evaluate.py backend/tests/test_evaluate_script.py
git commit -m "fix: validate index before rag evaluation"
```

## Task 3: Make data-audit defaults follow application settings

**Files:**
- Modify: `backend/tests/test_audit_data_script.py`
- Modify: `backend/scripts/audit_data.py`

- [ ] **Step 1: Add failing configured-path and CLI-override tests**

Append to `backend/tests/test_audit_data_script.py`:

```python
def test_parse_args_uses_configured_data_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_posts = tmp_path / "configured-posts.json"
    configured_topics = tmp_path / "configured-topics.json"
    configured = type(
        "ConfiguredPaths",
        (),
        {
            "raw_posts_path": configured_posts,
            "topic_rules_path": configured_topics,
        },
    )()
    monkeypatch.setattr(audit_data, "get_settings", lambda: configured)

    args = audit_data.parse_args([])

    assert args.posts == configured_posts
    assert args.topic_rules == configured_topics


def test_parse_args_explicit_paths_override_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = type(
        "ConfiguredPaths",
        (),
        {
            "raw_posts_path": tmp_path / "configured-posts.json",
            "topic_rules_path": tmp_path / "configured-topics.json",
        },
    )()
    explicit_posts = tmp_path / "explicit-posts.json"
    explicit_topics = tmp_path / "explicit-topics.json"
    monkeypatch.setattr(audit_data, "get_settings", lambda: configured)

    args = audit_data.parse_args(
        ["--posts", str(explicit_posts), "--topic-rules", str(explicit_topics)]
    )

    assert args.posts == explicit_posts
    assert args.topic_rules == explicit_topics
```

- [ ] **Step 2: Run the new tests and verify RED**

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_audit_data_script.py -q
```

Expected: failure because `audit_data` has no `get_settings` attribute and uses repository constants.

- [ ] **Step 3: Derive parser defaults from `Settings`**

Change the import in `backend/scripts/audit_data.py`:

```python
from backend.app.config import REPOSITORY_ROOT, get_settings
```

At the start of `parse_args`, before constructing arguments, add:

```python
    settings = get_settings()
```

Use these defaults:

```python
        default=settings.raw_posts_path,
```

and:

```python
        default=settings.topic_rules_path,
```

Keep the report output default under `REPOSITORY_ROOT/data/audit/reports` because it has no application setting.

- [ ] **Step 4: Run focused tests and Ruff and verify GREEN**

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_audit_data_script.py backend/tests/test_data_audit.py -q
backend/.venv/Scripts/python.exe -m ruff check backend/scripts/audit_data.py backend/tests/test_audit_data_script.py
```

- [ ] **Step 5: Commit configured audit paths**

```bash
git add backend/scripts/audit_data.py backend/tests/test_audit_data_script.py
git commit -m "fix: use configured paths for data audits"
```

## Task 4: Separate API liveness from RAG readiness

**Files:**
- Modify: `backend/tests/test_main.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add a failing liveness-isolation test**

Insert after `test_index_compatibility_maps_store_open_failure_to_unavailable`:

```python
def test_live_reports_process_without_checking_index(monkeypatch) -> None:
    compatibility_check = Mock(side_effect=AssertionError("index must not be opened"))
    monkeypatch.setattr(
        main,
        "get_index_compatibility",
        compatibility_check,
        raising=False,
    )

    response = api_request("GET", "/api/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    compatibility_check.assert_not_called()
```

- [ ] **Step 2: Run the test and verify RED**

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_main.py::test_live_reports_process_without_checking_index -q
```

Expected: HTTP 404 because `/api/live` does not exist.

- [ ] **Step 3: Add the typed liveness response and route**

Add to `backend/app/schemas.py` before `HealthResponse`:

```python
class LiveResponse(BaseModel):
    status: Literal["alive"] = "alive"
```

Extend the import in `backend/app/main.py`:

```python
from backend.app.schemas import ChatRequest, ChatResponse, HealthResponse, LiveResponse
```

Add after the root route and before `/api/health`:

```python
@app.get("/api/live", response_model=LiveResponse)
def live() -> LiveResponse:
    return LiveResponse()
```

- [ ] **Step 4: Run API tests and Ruff and verify GREEN**

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_main.py -q
backend/.venv/Scripts/python.exe -m ruff check backend/app/main.py backend/app/schemas.py backend/tests/test_main.py
```

- [ ] **Step 5: Commit the health boundary**

```bash
git add backend/app/main.py backend/app/schemas.py backend/tests/test_main.py
git commit -m "feat: expose api liveness separately"
```

## Task 5: Upgrade the vulnerable frontend test toolchain

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] **Step 1: Capture the failing development-dependency audit**

Run:

```powershell
npm --prefix frontend audit --omit=dev
npm --prefix frontend audit
```

Expected baseline: production audit exits 0 with 0 vulnerabilities; full audit exits 1 with 5 development-tool findings, including the Vitest critical advisory.

- [ ] **Step 2: Install mutually compatible fixed versions**

```powershell
npm --prefix frontend install --save-dev --save-exact vitest@4.1.10 @vitejs/plugin-react@6.0.3 jsdom@29.1.1
```

Update the Node engine in `frontend/package.json` to match the installed Vite toolchain:

```json
  "engines": {
    "node": "^20.19.0 || ^22.12.0 || >=24.0.0"
  },
```

Keep production Next.js and React versions unchanged.

- [ ] **Step 3: Verify audit and existing frontend compatibility**

```powershell
npm --prefix frontend audit --omit=dev
npm --prefix frontend audit
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

Expected: both audits report 0 vulnerabilities and all four frontend gates pass. If an audit still fails, do not use `npm audit fix --force`; inspect the exact dependency path and select a compatible explicit version.

- [ ] **Step 4: Commit the toolchain migration**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: update frontend test toolchain"
```

## Task 6: Extract a timeout-safe frontend chat client

**Files:**
- Create: `frontend/app/lib/chatApi.test.ts`
- Create: `frontend/app/lib/chatApi.ts`
- Create: `frontend/app/page.test.tsx`
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Write the failing HTTP-boundary tests**

Create `frontend/app/lib/chatApi.test.ts`:

```typescript
import { describe, expect, it, vi } from "vitest";

import { requestChat } from "./chatApi";

function httpResponse(
  body: string,
  status = 200,
  contentType = "application/json",
): Response {
  return new Response(body, {
    status,
    headers: { "Content-Type": contentType },
  });
}

describe("requestChat", () => {
  it("normalizes the API URL and maps a successful payload", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      httpResponse(
        JSON.stringify({
          answer: "최신 공지입니다.",
          sources: [],
          grounded: true,
          suggested_questions: ["다음 질문"],
          recent_notices: [],
        }),
      ),
    );

    const result = await requestChat("최근 공지", {
      apiUrl: "http://api.test/",
      fetchImpl: fetchImpl as typeof fetch,
    });

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://api.test/api/chat",
      expect.objectContaining({ method: "POST" }),
    );
    expect(result).toEqual({
      content: "최신 공지입니다.",
      sources: [],
      grounded: true,
      suggested_questions: ["다음 질문"],
      recent_notices: [],
    });
  });

  it("preserves a FastAPI detail message", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      httpResponse(JSON.stringify({ detail: "인덱싱을 먼저 실행하세요." }), 409),
    );

    await expect(
      requestChat("최근 공지", { fetchImpl: fetchImpl as typeof fetch }),
    ).rejects.toThrow("인덱싱을 먼저 실행하세요.");
  });

  it("hides an HTML error body behind a readable fallback", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      httpResponse("<html>proxy failure</html>", 502, "text/html"),
    );

    await expect(
      requestChat("최근 공지", { fetchImpl: fetchImpl as typeof fetch }),
    ).rejects.toThrow("답변을 불러오지 못했습니다.");
  });

  it("maps a network failure to a connection message", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("fetch failed"));

    await expect(
      requestChat("최근 공지", { fetchImpl: fetchImpl as typeof fetch }),
    ).rejects.toThrow("서버에 연결할 수 없습니다.");
  });

  it("aborts a request after the configured timeout", async () => {
    vi.useFakeTimers();
    try {
      const fetchImpl = vi.fn(
        (_input: RequestInfo | URL, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => {
              reject(new DOMException("aborted", "AbortError"));
            });
          }),
      );
      const pending = requestChat("최근 공지", {
        fetchImpl: fetchImpl as typeof fetch,
        timeoutMs: 50,
      });
      const rejection = expect(pending).rejects.toThrow(
        "답변 요청 시간이 초과되었습니다.",
      );

      await vi.advanceTimersByTimeAsync(50);
      await rejection;
    } finally {
      vi.useRealTimers();
    }
  });
});
```

- [ ] **Step 2: Run the HTTP tests and verify RED**

```powershell
npm --prefix frontend test -- app/lib/chatApi.test.ts
```

Expected: failure because `frontend/app/lib/chatApi.ts` does not exist.

- [ ] **Step 3: Implement the focused HTTP client**

Create `frontend/app/lib/chatApi.ts`:

```typescript
import type { RecentNotice, Source } from "../components/types";

const DEFAULT_TIMEOUT_MS = 15_000;
const DEFAULT_ERROR_MESSAGE = "답변을 불러오지 못했습니다.";

export type ChatReply = {
  content: string;
  sources: Source[];
  grounded?: boolean;
  suggested_questions: string[];
  recent_notices: RecentNotice[];
};

type RequestChatOptions = {
  apiUrl?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
};

class ChatApiError extends Error {}

function parseJsonObject(body: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(body);
    return value !== null && typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function responseErrorMessage(
  response: Response,
  payload: Record<string, unknown> | null,
  body: string,
): string {
  if (payload && typeof payload.detail === "string") return payload.detail;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.startsWith("text/plain") && body.trim()) return body.trim();
  return DEFAULT_ERROR_MESSAGE;
}

export async function requestChat(
  question: string,
  options: RequestChatOptions = {},
): Promise<ChatReply> {
  const apiUrl = (options.apiUrl ?? "http://localhost:8000").replace(/\/+$/, "");
  const fetchImpl = options.fetchImpl ?? fetch;
  const controller = new AbortController();
  const timeoutId = setTimeout(
    () => controller.abort(),
    options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  );

  try {
    const response = await fetchImpl(`${apiUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: controller.signal,
    });
    const body = await response.text();
    const payload = parseJsonObject(body);

    if (!response.ok) {
      throw new ChatApiError(responseErrorMessage(response, payload, body));
    }
    if (!payload || typeof payload.answer !== "string") {
      throw new ChatApiError("서버 응답 형식을 확인할 수 없습니다.");
    }

    return {
      content: payload.answer,
      sources: Array.isArray(payload.sources) ? (payload.sources as Source[]) : [],
      grounded:
        typeof payload.grounded === "boolean" ? payload.grounded : undefined,
      suggested_questions: Array.isArray(payload.suggested_questions)
        ? (payload.suggested_questions as string[])
        : [],
      recent_notices: Array.isArray(payload.recent_notices)
        ? (payload.recent_notices as RecentNotice[])
        : [],
    };
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ChatApiError("답변 요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.");
    }
    if (error instanceof ChatApiError) throw error;
    throw new ChatApiError("서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  } finally {
    clearTimeout(timeoutId);
  }
}
```

- [ ] **Step 4: Run the client tests and verify GREEN**

```powershell
npm --prefix frontend test -- app/lib/chatApi.test.ts
npm --prefix frontend run typecheck
```

- [ ] **Step 5: Add failing page-level success, suggestion, and timeout tests**

Create `frontend/app/page.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Home from "./page";
import { requestChat } from "./lib/chatApi";

vi.mock("./lib/chatApi", () => ({ requestChat: vi.fn() }));

const mockedRequestChat = vi.mocked(requestChat);

describe("Home", () => {
  beforeEach(() => {
    mockedRequestChat.mockReset();
    vi.stubGlobal(
      "requestAnimationFrame",
      (callback: FrameRequestCallback) => {
        callback(0);
        return 1;
      },
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it("renders a successful answer and its follow-up data", async () => {
    mockedRequestChat.mockResolvedValue({
      content: "현재 개설강좌 공지입니다.",
      sources: [],
      grounded: true,
      suggested_questions: ["수강신청 일정도 알려줘"],
      recent_notices: [],
    });
    render(<Home />);

    fireEvent.change(screen.getByLabelText("질문 입력"), {
      target: { value: "개설강좌 알려줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "질문 보내기" }));

    expect(await screen.findByText("현재 개설강좌 공지입니다.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "수강신청 일정도 알려줘" })).toBeEnabled();
  });

  it("sends an initial recommended question", async () => {
    mockedRequestChat.mockResolvedValue({
      content: "최근 공지입니다.",
      sources: [],
      grounded: true,
      suggested_questions: [],
      recent_notices: [],
    });
    render(<Home />);

    fireEvent.click(
      screen.getByRole("button", { name: "최근 수강신청 공지를 알려줘" }),
    );

    expect(mockedRequestChat).toHaveBeenCalledWith(
      "최근 수강신청 공지를 알려줘",
      expect.objectContaining({ apiUrl: expect.any(String) }),
    );
  });

  it("renders a timeout as a readable assistant message", async () => {
    mockedRequestChat.mockRejectedValue(
      new Error("답변 요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."),
    );
    render(<Home />);

    fireEvent.change(screen.getByLabelText("질문 입력"), {
      target: { value: "최근 공지 알려줘" },
    });
    fireEvent.click(screen.getByRole("button", { name: "질문 보내기" }));

    expect(
      await screen.findByText(
        "답변 요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
      ),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run the page tests and verify RED**

```powershell
npm --prefix frontend test -- app/page.test.tsx
```

Expected: mock assertions fail because `page.tsx` still calls `fetch` directly and never calls `requestChat`.

- [ ] **Step 7: Replace inline fetch/parsing in `page.tsx`**

Add:

```typescript
import { requestChat } from "./lib/chatApi";
```

Replace the initial assistant copy with:

```typescript
  content:
    "안녕하세요! 현재 제공 중인 금오공대 소프트웨어전공 공식 공지를 바탕으로 학사·진로 정보를 찾아드려요. 중요한 일정은 원문 링크에서 다시 확인해 주세요.",
```

Replace the complete `fetch`/`response.json()` block inside `try` with:

```typescript
      const reply = await requestChat(trimmed, { apiUrl });
      setMessages((current) => [
        ...current,
        {
          id: Date.now() + 1,
          role: "assistant",
          ...reply,
        },
      ]);
```

Leave the current catch/finally behavior in place. The page remains responsible for message state and focus; `requestChat` owns transport behavior.

- [ ] **Step 8: Run all frontend gates and verify GREEN**

```powershell
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

Expected: all component, client, and page tests pass; production build succeeds.

- [ ] **Step 9: Commit the frontend HTTP boundary**

```bash
git add frontend/app/lib/chatApi.ts frontend/app/lib/chatApi.test.ts frontend/app/page.tsx frontend/app/page.test.tsx
git commit -m "feat: harden frontend chat requests"
```

## Task 7: Wire configurable Compose health checks

**Files:**
- Create: `backend/tests/test_deployment_config.py`
- Modify: `compose.yaml`

- [ ] **Step 1: Write a failing static deployment-contract test**

Create `backend/tests/test_deployment_config.py`:

```python
from backend.app.config import REPOSITORY_ROOT


def test_compose_wires_configurable_url_and_process_healthchecks() -> None:
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}" in compose
    assert "http://localhost:8000/api/live" in compose
    assert "condition: service_healthy" in compose
    assert "fetch('http://localhost:3000')" in compose
```

- [ ] **Step 2: Run the deployment test and verify RED**

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_deployment_config.py -q
```

Expected: all four assertions fail against the current hardcoded/no-healthcheck Compose file.

- [ ] **Step 3: Add backend/frontend health checks and URL substitution**

Update `compose.yaml` so the relevant service sections contain:

```yaml
  backend:
    restart: unless-stopped
    build:
      context: .
      dockerfile: backend/Dockerfile
    env_file:
      - .env
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    volumes:
      - ./data:/app/data
      - ./chroma_db:/app/chroma_db
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - >-
          import urllib.request;
          urllib.request.urlopen('http://localhost:8000/api/live', timeout=3)
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

  frontend:
    restart: unless-stopped
    build:
      context: .
      dockerfile: frontend/Dockerfile
      args:
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}
    depends_on:
      backend:
        condition: service_healthy
    ports:
      - "${FRONTEND_PORT:-3000}:3000"
    healthcheck:
      test:
        - CMD
        - node
        - -e
        - >-
          fetch('http://localhost:3000')
          .then((response) => process.exit(response.ok ? 0 : 1))
          .catch(() => process.exit(1))
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
```

Do not make frontend startup depend on RAG readiness. The backend container checks `/api/live`; `/api/health` continues to report `needs_index` and other operational states after both processes start.

- [ ] **Step 4: Run static validation and conditional Docker validation**

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_deployment_config.py backend/tests/test_main.py -q
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose config
    docker compose build
} else {
    Write-Output "Docker unavailable: runtime Compose validation remains open."
}
```

Expected on the current host: Python tests pass and the explicit Docker-unavailable message is printed.

- [ ] **Step 5: Commit deployment configuration**

```bash
git add compose.yaml backend/tests/test_deployment_config.py
git commit -m "feat: add compose process health checks"
```

## Task 8: Correct root contributor and operator documentation

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `.env.example`

- [ ] **Step 1: Record the stale statements before editing**

```powershell
rg -n "약 100건|--seboard-limit 50|기본적으로 Selenium|No application manifest|Git history is not available|46건 baseline" README.md AGENTS.md .env.example
```

Expected: every stale statement listed above is found.

- [ ] **Step 2: Rewrite the README entry points with current behavior**

Use this opening paragraph:

```markdown
현재 추적 스냅샷의 금오공과대학교 소프트웨어전공 공식 공지 50건을 검색하고, 검색된 게시글만 근거로 답변하는 RAG 챗봇 프로토타입입니다. 답변에는 사용한 게시글의 제목·작성일·원문 링크와 함께 추천 질문·최근 공지가 표시됩니다. SE 게시판 데이터는 운영자 허가 또는 승인된 공식 API가 확보되기 전까지 제공하지 않습니다.
```

Make these exact operational changes:

```powershell
# dependency installation
npm --prefix frontend ci

# supported collection command
backend/.venv/Scripts/python.exe -m backend.scripts.crawl --kumoh-limit 50 --seboard-limit 0

# provider-matched evaluation example
$env:AI_PROVIDER="local"
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate --provider configured
```

Add these clarifications in prose:

- Chrome is needed only after written SE permission and only for the approved Selenium path.
- A positive `--seboard-limit` additionally requires `--seboard-permission-confirmed`; the flag records operator intent but does not replace permission.
- Reindexing depends on embedding provider/model, dimensions, chunking, source data, and topic rules. A chat-model-only change does not require reindexing.
- `/api/live` is process liveness; `/api/health` is RAG readiness.
- `NEXT_PUBLIC_API_URL` is embedded during the frontend Docker build, so changing it requires rebuilding the frontend image.
- Run both `npm audit --omit=dev` and `npm audit` during dependency reviews.

Remove the paragraph that presents Selenium as the normal current SE path; move API/Selenium details under the permission-gated explanation.

- [ ] **Step 3: Replace the stale `AGENTS.md` project guide**

Keep the same high-level headings but ensure the file states these exact rules:

```markdown
# Repository Guidelines

## Project Structure & Canonical Documentation

- `frontend/`: Next.js chat UI and colocated Vitest tests.
- `backend/app/`: FastAPI, RAG orchestration, retrieval, citations, and crawler implementations.
- `backend/scripts/`: collection, indexing, evaluation, and data-audit CLIs.
- `backend/tests/`: pytest unit and integration tests.
- `data/raw/posts.json`: current canonical source snapshot; generated candidates, reports, and indexes remain untracked.
- `docs/PROJECT_STATUS.md`: current counts, readiness, risks, and remaining verification.
- `docs/RAG_ARCHITECTURE.md`: stable RAG documentation index and invariants.
- `docs/rag/operations-evaluation.md`: authoritative operational commands.
- `docs/superpowers/**` and `docs/reference/**`: dated historical records; do not treat them as current operations.

## Build, Test, and Development Commands

Follow `README.md` for setup and `docs/rag/operations-evaluation.md` for the complete command set. Install backend development dependencies from `backend/requirements-dev.txt` and frontend dependencies with `npm ci`. The root quality workflow is `.github/workflows/quality.yml`.

## Coding, Testing, and Security

Use 2-space indentation for TypeScript/JSON and 4 spaces for Python. Use `PascalCase` React components, `camelCase` TypeScript functions, and `snake_case` Python functions. Add a failing test before behavior changes, mock paid APIs and mutable live pages, run `git diff --check`, and never commit `.env`, vector indexes, generated reports, build output, or secrets. SE collection remains disabled until written permission or an approved official API is documented.

## Commits and Pull Requests

Use focused Conventional Commits. Pull requests must list user-visible changes, verification evidence, and any schema, prompt, data-source, dependency, or environment-variable changes. Include UI screenshots when presentation changes materially.
```

- [ ] **Step 4: Clarify the historical threshold comment in `.env.example`**

Replace the 46-post comment with:

```dotenv
# 2026-07-14의 46건 historical tuning snapshot에서 노이즈 최고점 0.0924
# (scholarship-apply)와 참양성 최저점 0.1161(course-openings-lookup) 사이로
# 0.10을 선택했습니다. 현재 데이터 수는 docs/PROJECT_STATUS.md를 확인하고,
# 데이터/provider 변경 뒤에는 최소 30문항으로 다시 평가하세요.
```

- [ ] **Step 5: Verify the stale root statements are gone**

```powershell
rg -n "약 100건|--seboard-limit 50|기본적으로 Selenium|No application manifest|Git history is not available" README.md AGENTS.md .env.example
git diff --check -- README.md AGENTS.md .env.example
```

Expected: `rg` returns no matches and `git diff --check` emits no errors.

- [ ] **Step 6: Commit root documentation**

```bash
git add README.md AGENTS.md .env.example
git commit -m "docs: align setup and contributor guidance"
```

## Task 9: Establish canonical RAG documentation and remove stale implementation claims

**Files:**
- Modify: `docs/RAG_ARCHITECTURE.md`
- Modify: `docs/rag/overview.md`
- Modify: `docs/rag/providers.md`
- Modify: `docs/rag/retrieval-answering.md`
- Modify: `docs/rag/data-pipeline.md`
- Modify: `docs/rag/operations-evaluation.md`

- [ ] **Step 1: Add documentation precedence to `RAG_ARCHITECTURE.md`**

Add this section after the introduction:

```markdown
## 문서 우선순위

현재 수치·준비도·위험은 `PROJECT_STATUS.md`, 실행 명령은 `rag/operations-evaluation.md`, 지원 설정과 기본값은 `.env.example`을 기준으로 한다. 나머지 RAG 문서는 변하지 않는 구조와 동작을 설명한다. 날짜가 있는 `docs/superpowers/**`와 `docs/reference/**`는 작성 당시의 역사 자료이며 현재 운영 문서보다 우선하지 않는다.
```

Change the fast-decision rule to distinguish model roles:

```markdown
- 임베딩 provider·모델·차원을 바꾸면 `rag/providers.md`를 수정하고 전체 인덱스를 재생성한다. 답변 chat model만 바꾸는 경우에는 재인덱싱하지 않는다.
```

- [ ] **Step 2: Make `overview.md` structural rather than a second status page**

Replace the volatile status list with:

```markdown
## 현재 운영 상태

데이터 건수, 인덱스 청크 수, provider, 평가 결과와 준비도는 [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md)를 단일 기준으로 사용한다. 현재 구현은 로컬 hash embedding·extractive answer와 OpenAI embedding·Responses API 경로를 지원하며, 어느 provider든 strict index manifest가 일치할 때만 질의한다. SE 데이터 수집은 권한 또는 승인된 공식 API가 확보될 때까지 비활성이다.
```

Replace the expansion list with only genuinely unimplemented items:

```markdown
## 확장 우선순위

1. 운영자 허가 또는 승인된 공식 API 확보 후 SE 소스 계약·fixture 검증
2. BM25/vector hybrid 검색과 필요 시 reranker 비교 평가
3. PDF/HWP 첨부 텍스트 추출과 문서별 parser 분리
4. 증분 수집, 수정·삭제 감지, 인덱스 backup/restore
5. OpenAI 운영 quota 확보 후 local/OpenAI 품질·비용 A/B 평가
6. 요청 ID, 검색 점수, 선택 문서, 지연시간을 포함한 민감정보 없는 관측성
```

- [ ] **Step 3: Replace the obsolete provider warning with implemented manifest behavior**

Use this final paragraph in `providers.md`:

```markdown
인덱싱 성공 시 `CHROMA_PATH/index-manifest.json`에 provider, 임베딩 모델·차원, 청킹 설정, 컬렉션, 원본·주제 규칙 SHA-256, 청크 수와 signature fingerprint를 기록한다. API와 평가 CLI는 현재 설정으로 signature를 다시 계산해 manifest와 비교하며, 하나라도 다르면 provider를 호출하기 전에 fail-closed로 중단한다. `OPENAI_CHAT_MODEL`만 바뀐 경우에는 embedding signature가 그대로이므로 재인덱싱하지 않는다.
```

- [ ] **Step 4: Remove volatile chunk counts from retrieval documentation**

Replace:

```markdown
현재 79청크에서는 Chroma가 충분하다.
```

with:

```markdown
현재 단일 사용자·로컬 프로토타입 규모에서는 Chroma가 충분하다. 정확한 청크 수는 `PROJECT_STATUS.md`를 기준으로 한다.
```

- [ ] **Step 5: Put the SE prohibition first in `data-pipeline.md`**

Replace the SE subsection with:

```markdown
### SE 게시판(비활성)

현재 `robots.txt`가 전체 자동 수집을 금지하므로 운영자 서면 허가 또는 승인된 공식 API를 확보하기 전에는 SE 수집을 실행하지 않는다. 공용 CLI는 `--seboard-limit 0`이 기본이며, 양수 limit에는 `--seboard-permission-confirmed`가 필요하다. 이 확인 옵션은 권한 자체를 대신하지 않는다.

권한이 문서화된 이후에만 승인 범위 안에서 공개 JSON API를 우선하고, 허용된 경우에 한해 headless Selenium을 보조 경로로 사용한다. 로그인 우회, CAPTCHA 무력화, 접근제어 회피는 범위 밖이다. 부분 성공 결과는 운영 원본이 아니라 `data/raw/candidates/`에서 사람이 URL·날짜·소스를 검토한다.
```

Change “100건 규모” to “현재 프로토타입 규모” in the chunking rationale.

- [ ] **Step 6: Make operations commands provider-safe and deployment-aware**

In `operations-evaluation.md`:

1. Label the environment table “주요 환경변수” and add `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL`, `BACKEND_PORT`, and `FRONTEND_PORT`.
2. Document that `NEXT_PUBLIC_API_URL` is a frontend build-time variable.
3. Keep the supported crawl command at `--seboard-limit 0` and document the explicit acknowledgement requirement for any positive value.
4. Add `/api/live` as process liveness and retain `/api/health` as the readiness matrix.
5. Replace the automatic evaluation example with:

```powershell
$env:AI_PROVIDER="local"
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate --provider configured
```

6. Add this safety explanation:

```markdown
`--provider configured`는 인덱싱에 사용한 현재 `AI_PROVIDER` 설정을 그대로 사용한다. `--provider local`은 local로 만든 인덱스를 평가할 때만 사용한다. 평가 CLI는 strict manifest를 먼저 검사하므로 provider·모델·차원·데이터·청크 수가 다르면 첫 질문 전에 exit 2로 중단한다.
```

7. Add Compose verification:

```powershell
docker compose config
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/api/live
Invoke-RestMethod http://localhost:8000/api/health
```

- [ ] **Step 7: Verify stale RAG claims are gone**

```powershell
rg -n "46건|79청크|fingerprint를 검증하지 않는다|embedding fingerprint 저장·검증" docs/RAG_ARCHITECTURE.md docs/rag
git diff --check -- docs/RAG_ARCHITECTURE.md docs/rag
```

Expected: no stale implementation claims and no whitespace errors.

- [ ] **Step 8: Commit canonical RAG documentation**

```bash
git add docs/RAG_ARCHITECTURE.md docs/rag
git commit -m "docs: align rag architecture with runtime safeguards"
```

## Task 10: Run the full gate and publish current status/handoff

**Files:**
- Modify: `docs/PROJECT_STATUS.md`
- Create: `docs/superpowers/handoffs/2026-07-15-maintainability-operational-safety-handoff.md`

- [ ] **Step 1: Run the complete backend gate**

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests --cov=backend.app --cov=backend.scripts --cov-config=backend/pyproject.toml --cov-report=term-missing
backend/.venv/Scripts/python.exe -m ruff check backend
```

Expected: every backend test passes and total product-code coverage remains at least 85%.

- [ ] **Step 2: Run the complete frontend and dependency gate**

```powershell
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend audit --omit=dev
npm --prefix frontend audit
```

Expected: every frontend gate passes and both audits report 0 vulnerabilities.

- [ ] **Step 3: Validate repository and deployment invariants**

```powershell
git diff --check
git status --short
rg -n "약 100건|--seboard-limit 50|현재 79청크|fingerprint를 검증하지 않는다|No application manifest|Git history is not available" README.md AGENTS.md docs .env.example
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_deployment_config.py -q
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose config
} else {
    Write-Output "Docker unavailable: compose runtime verification not completed."
}
```

Expected: no whitespace errors, no stale canonical statements, deployment contract test passes, and current-host Docker limitation is explicit.

- [ ] **Step 4: Update `PROJECT_STATUS.md` from measured outputs**

Change the header to the feature branch and link the new handoff. Record the exact test count and coverage printed in Step 1 and the exact frontend file/test count printed in Step 2. Update these status conclusions:

```markdown
- 공용 수집 CLI는 SE 수집을 기본 비활성화하고, 양수 limit을 권한 확인 없이 실행하지 않는다.
- 평가 CLI는 API와 같은 strict manifest 검사를 사용해 provider·설정·데이터가 다른 인덱스를 첫 질문 전에 차단한다.
- 데이터 감사 기본 경로는 `RAW_POSTS_PATH`와 `TOPIC_RULES_PATH`를 따른다.
- 프론트엔드 요청은 별도 client에서 15초 timeout, non-JSON 오류, FastAPI detail, 네트워크 실패를 읽을 수 있는 메시지로 변환한다.
- `/api/live`와 `/api/health`를 분리했고 Compose에는 process healthcheck와 build-time API URL 전달이 있다.
- production 및 development npm audit가 모두 0건이다.
- Docker가 없는 현재 호스트에서는 정적 구성만 검증했으며 실제 build·health transition은 외부 환경 검증이 남아 있다.
```

Move frontend fetch integration, Docker healthcheck, and dependency warning review from open work to locally completed work. Keep these items open:

- actual Docker build/start/health transition on a Docker host
- 390px/1280px browser E2E and visual regression
- remote GitHub Actions/branch protection verification
- SE permission/approved API, stale course-opening source, and empty graduation source
- observability, rate limiting, backup/restore, and incremental ingestion

- [ ] **Step 5: Create the handoff with exact entry points**

Create `docs/superpowers/handoffs/2026-07-15-maintainability-operational-safety-handoff.md` with these sections and concrete results from the commands above:

```markdown
# Maintainability And Operational Safety Handoff

## Outcome

- The public crawl CLI defaults SE collection to zero and rejects a positive limit before crawler construction unless operator permission is explicitly acknowledged.
- Evaluation uses the same strict manifest compatibility check as the API, and data-audit defaults follow application paths.
- Frontend HTTP behavior is isolated behind a timeout-safe client while answer sources, recommended questions, and recent notices keep their existing API contract.
- API liveness is separate from RAG readiness; Compose wires process health ordering and the build-time frontend API URL.
- The frontend test toolchain has no production or development findings in `npm audit`.
- Canonical documentation now separates current operations from dated historical records.

## Commits

Use `git log --oneline b99f997..HEAD` as the immutable commit list. The branch contains focused commits for the design, execution plan, crawler guard, evaluation guard, audit paths, liveness, frontend dependency update, frontend HTTP client, Compose health checks, canonical documentation, and final verification record.

## Verification Evidence

- The exact backend test count and product-code coverage are recorded in `docs/PROJECT_STATUS.md`; coverage is at least the enforced 85% gate.
- Ruff, frontend Vitest, TypeScript, ESLint, and Next.js production build pass.
- `npm audit --omit=dev` and full `npm audit` both report zero vulnerabilities.
- `git diff --check` and the static Compose deployment contract test pass.

## Explicitly Unverified

State that Docker runtime build/start/health transitions were not run on the current host when Docker remains unavailable. Do not describe static checks as runtime proof.

## Next Entry Point

1. Run Docker Compose on a Docker-enabled host and record `docker compose ps` plus `/api/live` and `/api/health` results.
2. Run 390px and 1280px browser E2E for success, server error, timeout, suggestion reuse, sources, and recent notices.
3. Confirm remote GitHub Actions and required branch protection after push.
4. Do not enable SE collection without written permission or an approved API.

## Security

No secret values are recorded. `.env`, API keys, passwords, and bearer tokens remain excluded.
```

- [ ] **Step 6: Verify status/handoff consistency**

```powershell
git diff --check -- docs/PROJECT_STATUS.md docs/superpowers/handoffs/2026-07-15-maintainability-operational-safety-handoff.md
git log --oneline b99f997..HEAD
git status --short
```

- [ ] **Step 7: Commit the final status and handoff**

```bash
git add docs/PROJECT_STATUS.md docs/superpowers/handoffs/2026-07-15-maintainability-operational-safety-handoff.md
git commit -m "docs: record maintainability verification"
```

## Task 11: Final independent review checkpoint

**Files:**
- Review only: all files changed by `git diff b99f997...HEAD`

- [ ] **Step 1: Inspect scope and commit structure**

```powershell
git diff --stat b99f997...HEAD
git diff --name-status b99f997...HEAD
git log --oneline --decorate b99f997..HEAD
```

Expected: no edits to `backend/app/crawling/seboard.py`, raw data, generated reports, Chroma indexes, secrets, or unrelated historical records.

- [ ] **Step 2: Review behavioral boundaries**

Confirm directly from code and tests:

- crawler guard executes before `SeBoardCrawler` construction;
- evaluation compatibility executes before provider construction and question evaluation;
- CLI path overrides beat configured audit defaults;
- `/api/live` never opens Chroma while `/api/health` still reports readiness details;
- `requestChat` clears its timer in every outcome and never shows HTML/JSON parse internals;
- frontend still renders sources, recommended questions, and recent notices;
- Compose waits for process liveness, not an already indexed RAG state;
- docs distinguish current canonical guidance from dated history.

- [ ] **Step 3: Re-run the complete gate after review fixes**

Use the exact commands from Task 10 Steps 1–3. Any review fix must be followed by its focused test and then this complete gate.

- [ ] **Step 4: Leave the branch clean and ready for integration**

```powershell
git status --short --branch
```

Expected: `## codex/maintainability-audit` with no modified or untracked files.
