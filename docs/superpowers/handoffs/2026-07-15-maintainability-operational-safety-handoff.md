# Maintainability And Operational Safety Handoff

## Outcome

Task 10 ran the requested local backend, frontend, invariant, focused deployment, dependency, and Docker availability gates on branch `codex/maintainability-audit` at HEAD `55cb283`, using base `b99f997`. The code gates passed with the exact results below. This is a local verification handoff only: the branch was not pushed or merged, Docker runtime was not available, browser E2E was not run, and raw data/index/evaluation/audit numbers were not re-executed.

Locally completed before this handoff:

- frontend fetch integration with timeout, network/non-JSON/detail fallback, runtime payload and link safety, while preserving sources/suggested/recent fields;
- frontend dependency review, including production and full npm audit;
- Compose static health contracts for process liveness, backend ordering, and build-time frontend API URL wiring.

Operational boundary decisions remain explicit: SE public crawl defaults to 0, a positive limit requires an acknowledgement flag, but the technical guard does not validate actual permission; evaluation checks the strict manifest before provider creation and before the first question; audit defaults come from configured `RAW_POSTS_PATH`/`TOPIC_RULES_PATH` and explicit path options win.

## Commits

The immutable list is the exact output of `git log --oneline b99f997..HEAD` captured before the documentation commit:

```text
55cb283 docs: clarify operational enforcement boundaries
c982a68 docs: align manifest and pipeline versioning claims
c99bc2c docs: align rag architecture with runtime safeguards
38f1600 docs: clarify provider threshold and compose prerequisites
6d7be3b docs: clarify selenium permission boundary
eb4d1f2 docs: align setup and contributor guidance
67fd096 test: harden compose contract parsing
c08ef28 test: harden compose deployment contracts
dc51fb8 test: scope deployment healthcheck contracts
edba132 feat: add compose process health checks
e29eb9d fix: enforce exact public endpoint mentions
392625b fix: distinguish safe URLs from error paths
3cc07d5 fix: generalize error path filtering
74e6f3c fix: hide generic exception details
6ea6cdf fix: reject unsafe chat payload values
c70d452 fix: validate frontend chat responses
cdc1213 test: assert FastAPI 409 detail handling
25f029c feat: harden frontend chat requests
d20087d fix: restore complete cross-platform frontend lockfile
638c09f fix: regenerate frontend lockfile for vitest toolchain
c749837 chore: update frontend test toolchain
b70c370 feat: expose api liveness separately
5c3a174 test: cover partial audit path defaults
5e785e3 fix: defer audit cli settings resolution
1cc5182 fix: use configured paths for data audits
27b15fa fix: validate index before rag evaluation
cc85a9f fix: disable unapproved seboard collection
66ca3db docs: add maintainability implementation plan
29ccd12 docs: define maintainability improvement design
```

The list includes the review-fix and hardening commits for frontend HTTP/error safety, public endpoint filtering, Compose parsing/health contracts, audit path handling, evaluation ordering, and SE crawl permission boundaries. The two documentation files in this handoff are the only intended changes for Task 10.

## Verification Evidence

### Backend

Command:

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests --cov=backend.app --cov=backend.scripts --cov-config=backend/pyproject.toml --cov-report=term-missing
```

Exact measured result:

```text
TOTAL                              1659    124    93%
Required test coverage of 85.0% reached. Total coverage: 92.53%
170 passed in 9.24s
```

Command:

```powershell
backend/.venv/Scripts/python.exe -m ruff check backend
```

Exact result: `All checks passed!` (exit 0).

### Frontend

```powershell
npm --prefix frontend test
```

Exact measured result: `Test Files 5 passed (5)` and `Tests 76 passed (76)`; Vitest duration `3.34s`.

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

All three exited 0. The build reported Next `15.5.20`, compiled successfully, generated static pages `(4/4)`, and emitted static routes `/` and `/_not-found`.

Next build changed the generated `frontend/next-env.d.ts`. The pre-build SHA-256 was `A3EA130D80CDE31C5180AF37457E5D1318A1E30888C14BA4624F117E382987C`; the post-build SHA-256 was `85AE5AEE75F011967CF2D25CBC342F62D69314E9D925F7F4AA3456FC2CFFCCA6`. The generated change was reverted, and the final hash returned to the pre-build value.

### Dependency and invariant gates

```powershell
npm --prefix frontend audit --omit=dev
npm --prefix frontend audit
```

Both commands exited 0 with exact output `found 0 vulnerabilities`.

```powershell
git diff --check
```

Exited 0.

Canonical stale search over `README.md`, `AGENTS.md`, `.env.example`, `docs/PROJECT_STATUS.md`, `docs/RAG_ARCHITECTURE.md`, and `docs/rag` returned exact output:

```text
stale canonical search: no matches
```

A broader repository search found matches only in historical plan/spec text that documents the old-state checks; those historical records were not treated as canonical claims.

### Focused deployment and Docker

Command:

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_deployment_config.py -q
```

Exact output:

```text
.......                                                                  [100%]
```

This is 7 static deployment-contract tests covering Compose healthchecks, backend liveness, frontend ordering, and build-time API URL wiring.

Docker availability check returned:

```text
docker executable: unavailable
```

Therefore `docker compose config`, `docker compose build`, `docker compose up`, `docker compose ps`, and actual healthy/unhealthy transitions were not run. Static contract evidence is not Docker runtime evidence.

### Prior data snapshot boundary

The prior measured snapshot remains 50 posts, 84 chunks, 30/30 evaluation, and 3 audit warnings, sourced from the previous `PROJECT_STATUS.md` snapshot dated 2026-07-15. Task 10 did not rerun raw data counts, topic dates, indexing, evaluation, or audit, so these numbers are not current gate measurements.

### Documentation verification after edits

The post-document verification to run before commit is:

```powershell
git diff --check -- docs/PROJECT_STATUS.md docs/superpowers/handoffs/2026-07-15-maintainability-operational-safety-handoff.md
Test-Path docs/PROJECT_STATUS.md
Test-Path docs/superpowers/handoffs/2026-07-15-maintainability-operational-safety-handoff.md
git status --short
git log --oneline b99f997..HEAD
```

The final status must show only the two documentation files before the documentation commit, with no `frontend/next-env.d.ts` change.

## Explicitly Unverified

- Docker-enabled host: actual Compose config parsing, image builds, start-up, process health, and `/api/live`/`/api/health` transitions.
- 390px and 1280px browser E2E plus visual regression for success, server error, timeout, suggestion, source, and recent-notice flows.
- Remote GitHub Actions execution and branch protection required checks after push.
- SE permission/approved API, including scope and canonical source approval.
- Whether the existing `course_openings` source is stale against the official current source.
- Whether the empty `graduation` source needs a new approved source or an explicit empty-state UX.
- Raw candidate retrieval score diagnostic for threshold calibration; the prior evaluation pass is not calibration evidence.
- Production observability, rate limiting, backup/restore, and incremental ingestion.

## Next Entry Point

Execute in this order:

1. On a Docker-enabled host, run `docker compose config`, `docker compose up -d --build`, `docker compose ps`, then record backend `/api/live` and `/api/health` plus frontend health transitions. Keep static and runtime evidence separate.
2. Run 390px/1280px browser E2E and visual regression for success, server error, timeout, suggestion, source, and recent flows.
3. Push this branch, inspect remote GitHub Actions, and verify branch protection required checks. Do not report merge/push before those operations succeed.
4. Obtain and record SE permission or an approved API before any positive crawl limit; the acknowledgement flag alone is insufficient.
5. Run the raw candidate score diagnostic before changing thresholds; treat current evaluation pass/fail as a separate signal.

Recommended provider-matched operations:

```powershell
$env:AI_PROVIDER="local"
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate --provider configured
backend/.venv/Scripts/python.exe -m backend.scripts.audit_data
npm --prefix frontend audit --omit=dev
npm --prefix frontend audit
```

## Security

- No `.env` content, API key, password, bearer token, or other secret was recorded. If a sensitive value is encountered during future handoff work, record `민감정보 제거됨` only.
- Do not treat `--seboard-permission-confirmed` as permission validation. Use only documented operator permission or an approved public API; do not bypass login, CAPTCHA, or access controls.
- Keep user-facing errors free of stack traces, secrets, local absolute paths, and unsafe links. The frontend runtime payload/link checks and backend liveness/readiness split are safety boundaries, not substitutes for production monitoring.
