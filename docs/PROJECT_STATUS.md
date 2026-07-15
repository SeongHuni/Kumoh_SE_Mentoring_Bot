# SE Mentor Bot 프로젝트 상태와 다음 작업

> 기준일: 2026-07-15
> 기준 브랜치: `codex/maintainability-audit`
> 검증 기준 base: `b99f997`
> 최신 인수인계: [`superpowers/handoffs/2026-07-15-maintainability-operational-safety-handoff.md`](superpowers/handoffs/2026-07-15-maintainability-operational-safety-handoff.md)

이 문서는 Task 10 전체 gate 이후의 현재 구현·검증 상태와 외부 확인이 필요한 운영 위험을 관리한다. 로컬 코드 gate와 외부 데이터·Docker·브라우저·원격 CI 검증은 서로 분리해 기록한다. 현재 브랜치가 push되었거나 merge되었다고 주장하지 않는다.

## 1. 현재 결론

- 백엔드 전체 pytest는 `170 passed`, 총 coverage는 `92.53%`로 85% gate를 넘었고 Ruff도 통과했다.
- 프론트엔드는 Vitest `5 files / 76 tests` 통과, TypeScript·ESLint·Next production build 통과, production/development 의존성 audit 모두 `0 vulnerabilities`다.
- strict index manifest는 평가에서 provider를 만들거나 첫 질문을 처리하기 전에 확인된다. provider·모델·차원·원본·주제 규칙·청크 수가 맞지 않으면 fail-closed로 중단한다.
- `audit_data`는 기본적으로 설정된 `RAW_POSTS_PATH`와 `TOPIC_RULES_PATH`를 사용하며, `--posts`·`--topic-rules` 명시값이 있으면 각각의 override가 우선한다.
- SE public crawl은 기본값이 `0`이고 양수 limit에는 acknowledgement가 필요하다. 이 기술적 guard는 실제 운영자 허가나 API 사용 권한 자체를 검증하지 않는다.
- frontend chat client는 15초 timeout, network/non-JSON/detail 처리, runtime payload 및 link safety 검사를 적용하며 `sources`·`suggested_questions`·`recent_notices` 필드를 보존한다.
- `/api/live`는 process liveness, `/api/health`는 index/provider readiness로 분리되어 있다. Compose는 process health ordering과 build-time `NEXT_PUBLIC_API_URL`을 사용한다.
- fetch integration, dependency review, Compose static health contracts는 로컬에서 완료됐다. Docker executable이 없는 현재 호스트에서는 static 확인만 했으며 실제 runtime 증거는 없다.
- 기존 데이터 수치(50 posts, 84 chunks, 30 eval, 3 audit warnings)는 기존 검증 snapshot으로만 보존한다. Task 10에서는 raw data·index·evaluation·audit를 재실행하지 않았다.
- 이 브랜치의 검증 결론은 로컬 worktree 범위다. branch push, merge, remote GitHub Actions, branch protection은 확인하지 않았다.

핵심 결정 3개:

1. 로컬 code gate의 수치와 기존 data snapshot을 분리해 기록하고, 재실행하지 않은 데이터 수치로 최신 상태를 주장하지 않는다.
2. SE 수집은 기본 비활성·명시 acknowledgement로 막되, acknowledgement를 실제 권한 증명으로 오해하지 않으며 승인된 API 또는 서면 허가를 별도 조건으로 둔다.
3. manifest/readiness와 frontend 오류·링크 안전성은 fail-closed로 유지하고, Docker·브라우저·원격 CI 검증은 별도 환경에서 증거를 추가한다.

## 2. 단계별 진행도

| 영역 | 상태 | 현재 근거 | 남은 조건 |
| --- | --- | --- | --- |
| 백엔드 RAG·manifest | 로컬 검증 통과 | 170 tests, 92.53% coverage, Ruff, strict manifest 회귀 | provider-matched 실제 평가 재실행과 threshold calibration |
| 데이터 수집 안전성 | 로컬 guard 완료 | SE default 0, positive acknowledgement gate, partial 후보 격리 | SE permission/approved API, 최신성·소스 검증 |
| 데이터 감사 | 로컬 동작 검증 완료 | configured path defaults와 explicit overrides 테스트 | stale course_openings, empty graduation, 실제 snapshot 재검증 |
| frontend | 로컬 gate 통과 | 5 files/76 tests, typecheck, lint, build | 390px/1280px browser E2E와 visual regression |
| 배포 계약 | static 검증 완료 | focused deployment pytest 7 tests, liveness health contracts | Docker-enabled host의 config/build/start/healthy transitions |
| 의존성 | 로컬 audit 통과 | `npm audit --omit=dev`와 full `npm audit` 모두 0 | 정기 review 및 remote CI 확인 |
| CI·branch protection | 미확인 | 로컬 명령만 실행 | push 후 GitHub Actions와 required checks/branch protection |
| branch handoff | 문서 기록 완료 | Task 10 verification target before status/handoff documentation: `55cb283`; first status/handoff record commit: `34d1270`; current HEAD/count는 `git rev-parse HEAD`와 `git rev-list --count b99f997..HEAD`로 확인 | 사용자의 push/merge 절차에서 원격 상태 확인 |
| 운영 안정성 | 미착수 | 계획과 정적 계약만 존재 | observability, rate limit, backup/restore, incremental ingestion |

## 3. Task 10 code gate 측정값

| 검증 | 정확한 결과 |
| --- | --- |
| backend pytest + coverage | `170 passed in 9.24s`; TOTAL `1659` statements, `124` missed, `93%` table coverage; final `92.53%`; required `85.0%` reached |
| backend Ruff | `All checks passed!` |
| frontend Vitest | `Test Files 5 passed (5)`; `Tests 76 passed (76)`; duration `3.34s` |
| frontend typecheck | exit 0 |
| frontend lint | exit 0 |
| frontend production build | exit 0; Next `15.5.20`; static routes `/`와 `/_not-found`, 4 pages generated |
| frontend production audit | `found 0 vulnerabilities` |
| frontend full audit | `found 0 vulnerabilities` |
| focused deployment pytest | `....... [100%]` — 7 static Compose/Docker contract tests |
| `git diff --check` | exit 0 |
| canonical stale search | Task10 canonical obsolete search over `README.md`, `AGENTS.md`, `.env.example`, `docs/PROJECT_STATUS.md`, `docs/RAG_ARCHITECTURE.md`, and `docs/rag` did not include `46건` and returned exact output `canonical obsolete search: no matches`. Separate targeted search found exactly one `46건` occurrence at `docs/rag/operations-evaluation.md:117`. It is an allowed historical local threshold-calibration context, not a current count. A broader repository/historical-docs search retains this intentional threshold occurrence, alongside historical plan/spec text that documents old-state checks; none are canonical current-count claims. |
| Docker | executable unavailable; `docker compose config`, build, ps, start, and health transition not run |

Next build가 `frontend/next-env.d.ts`를 생성 변경했다. pre-build SHA-256 `A3EA130D80CDE31C5180AF37457E5D1318A1E30888C14BA4624F117E382987C4`, post-build `85AE5AEE75F011967CF2D25CBC342F62D69314E9D925F7F4AA3456FC2CFFCCA6`를 확인했고, 생성 변경은 원복했다. 최종 worktree에서 tracked 변경은 이 문서와 handoff만 남긴다.

## 4. 기존 데이터 검증 snapshot

다음 수치는 **기존 검증 snapshot**이다. 출처는 2026-07-15 이전 `PROJECT_STATUS.md`의 last measured snapshot이며 Task 10에서 재실행하지 않았다. code gate 측정값과 혼동하지 않는다.

| 항목 | 기존 snapshot 값 |
| --- | --- |
| 저장 게시글 | 50 posts (`kumoh=50`, `seboard=0`) |
| 게시일 범위 | 2024-09-04 ~ 2026-06-30 |
| 로컬 인덱스 | 84 chunks, prior manifest fingerprint prefix `9fe1fee46fbf` |
| 평가 | 30/30, exit 0 |
| 데이터 감사 | 3 warnings, exit 1 |

기존 topic snapshot: `general` 15 (2026-06-17), `career` 14 (2026-06-30), `registration` 12 (2026-06-16), `scholarship` 6 (2026-06-17), `capstone` 2 (2026-03-19), `course_openings` 1 (2025-08-07), `graduation` 0 (없음). 이 날짜와 건수는 현재 live source의 최신성을 증명하지 않는다.

## 5. 유지된 운영 정책

### 질문·근거·provider 순서

- 평가 CLI는 `--provider configured`로 현재 `AI_PROVIDER` 설정과 인덱싱 provider를 맞출 수 있다. `--provider local`은 local 인덱스로 평가할 때만 사용한다.
- 평가와 chat은 strict manifest를 먼저 확인한다. 불일치 시 provider 생성 또는 첫 질문 전에 중단하며, 인덱스 재생성 없이는 질문을 진행하지 않는다.
- 기간·학기·제목 marker·동의어 근거가 맞지 않으면 `grounded=false`로 거절하고 answer provider를 호출하지 않는다.
- raw candidate는 운영 원본 `RAW_POSTS_PATH`를 덮어쓰지 않고 `data/raw/candidates/`에 격리한다.

### SE 게시판

- `--seboard-limit` 기본값은 0이다.
- 양수 limit에는 `--seboard-permission-confirmed`가 필요하지만, 이 flag는 실제 서면 허가·승인된 API 권한의 존재를 자동 증명하지 않는다.
- 승인 전에는 Selenium/API 수집을 실행하지 않는다. 로그인 우회·CAPTCHA 무력화·접근제어 회피는 범위 밖이다.

### frontend·deployment

- 15초 timeout과 abort, network/non-JSON/HTTP detail fallback을 제공한다.
- 성공 payload의 answer, HTTP/HTTPS source URL, source/recent metadata, suggestions를 runtime에서 검증한다.
- 오류 detail은 HTML, traceback, secret/path, unsafe endpoint/link를 제거하거나 generic fallback으로 대체한다.
- Compose backend healthcheck는 `/api/live`, frontend healthcheck는 process HTTP 응답을 확인하며 frontend는 backend `service_healthy`를 기다린다.
- `NEXT_PUBLIC_API_URL`은 Docker build-time에 image에 삽입되므로 변경 후 frontend image 재빌드가 필요하다. 이는 runtime health proof가 아니다.

## 6. 현재 검증 명령과 운영 명령

Task 10에서 실행한 gate는 handoff에 명령별 exact evidence로 기록했다. 운영 재검증 시 provider를 맞추는 권장 순서는 다음과 같다.

```powershell
$env:AI_PROVIDER="local"
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate --provider configured
backend/.venv/Scripts/python.exe -m backend.scripts.audit_data
```

`--provider configured`는 현재 `AI_PROVIDER` 설정을 사용해 provider·모델이 맞는 인덱스를 평가한다. 데이터·provider·embedding·chunk 설정을 바꾸면 index → evaluate → audit 순서로 다시 실행한다.

```powershell
npm --prefix frontend audit --omit=dev
npm --prefix frontend audit
docker compose config
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/api/live
Invoke-RestMethod http://localhost:8000/api/health
```

마지막 다섯 Docker 명령은 Docker-enabled host에서만 실행한다. 현재 호스트에서는 Docker가 없어 static Compose contract만 검증됐다.

## 7. Open only

1. Docker enabled host에서 actual `docker compose config`, image build, start, `docker compose ps`, backend/frontend healthy transitions와 `/api/live`·`/api/health` 결과를 기록한다. static contract를 runtime proof로 바꾸지 않는다.
2. 390px/1280px browser E2E와 visual regression을 success, server error, timeout, suggestion, source, recent 흐름으로 실행한다.
3. push 후 remote GitHub Actions와 branch protection required checks를 확인한다. 이 branch가 merged/pushed라고 말하지 않는다.
4. SE permission/approved API를 확보하고, robots·사용 범위·canonical source를 문서화한다. acknowledgement flag만으로 권한을 대체하지 않는다.
5. `course_openings`의 stale source와 `graduation`의 empty source를 공식 원문 또는 명시적 empty UX로 처리한다.
6. raw candidate score diagnostic을 수집해 threshold를 보정한다. 기존 eval pass는 calibration 근거가 아니다.
7. observability, rate limit, backup/restore, incremental ingestion을 운영 범위로 설계·검증한다.

## 8. 문서 유지 규칙

- 현재 결론·volatile gate 수치는 이 문서를 status authority로 갱신한다. handoff에는 해당 세션의 immutable evidence만 남긴다.
- data/index/evaluation/audit 수치를 재실행하지 않았으면 반드시 기존 검증 snapshot으로 표시한다.
- 로컬 코드 통과와 공식 source 권한·Docker runtime·브라우저·원격 CI 확인을 같은 완료 주장으로 합치지 않는다.
- `.env`, API key, password, bearer token은 기록하지 않고 `민감정보 제거됨`으로 대체한다. 파일 경로는 기록할 수 있지만 `.env` 내용은 기록하지 않는다.
