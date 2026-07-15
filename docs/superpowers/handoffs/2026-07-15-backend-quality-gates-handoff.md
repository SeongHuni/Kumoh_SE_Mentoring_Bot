# Backend Quality Gates Handoff

> 작성일: 2026-07-15
> 브랜치: `codex/backend-quality-gates`
> 기준점: `main`의 `3c016de`
> worktree: `.worktrees/backend-quality-gates`
> 상태: 로컬 구현·인덱싱·회귀 검증 완료, 원격 CI와 main 통합은 미실행

## 1. 다음 작업자의 진입점

이 브랜치는 RAG 답변 품질 기능을 바꾸기보다 오래된 또는 잘못 구성된 벡터 인덱스로 답변하는 위험을 차단하고, 제품 코드 coverage와 CI 기준을 고정한다. 사용자가 이번 범위에서 SE 게시판 관련 구현을 제외했으므로 `backend/app/crawling/seboard.py`, SE fixture, 크롤링 권한 정책은 변경하지 않았다.

처음 확인할 명령:

```powershell
Set-Location .worktrees/backend-quality-gates
git status --short --branch
git log --oneline 3c016de..HEAD
backend/.venv/Scripts/python.exe -c "from backend.app.main import health; print(health().model_dump())"
```

worktree가 없다면 저장소 루트에서 `git worktree add .worktrees/backend-quality-gates codex/backend-quality-gates`로 다시 연결한다. 현재 로컬 Chroma와 생성 보고서는 Git에서 제외된다. 다른 PC나 새 clone에서는 `backend/.venv/Scripts/python.exe -m backend.scripts.index --reset`을 먼저 실행해야 health가 `ready`가 된다.

## 2. 완료한 구현과 커밋

| 커밋 | 내용 |
| --- | --- |
| `78b3cdc` | backend 품질 gate 설계 문서 |
| `ac88849` | TDD 기반 7개 Task 구현 계획 |
| `27550bb` | 명시적 임베딩 차원과 청킹 설정, provider 전달 계약 |
| `8ebd50e` | strict `index-manifest.json`, SHA-256 fingerprint와 호환성 reason |
| `16b2014` | 비어 있지 않은 인덱스의 `--reset` 강제, 실패 시 manifest 무효화, 성공 시 atomic 기록 |
| `b19af2d` | health 상태 분리와 오래된 인덱스 chat 차단, fingerprint 기반 RAG cache |
| `afdb26a` | 제품 코드 line coverage 85% gate와 회귀 테스트 보강 |
| `7a1f19d` | backend/frontend GitHub Actions와 운영·검증 문서 |
| `9a908cc` | 외부 reset 뒤 health가 삭제된 Chroma collection handle을 재사용하는 결함 수정 |
| `fb01183` | frontend `typecheck` package script로 CI cwd 해석 제거 |
| `5ac701d` | 동일 입력 재인덱싱에서도 manifest 세대별로 RAG service를 교체 |

마지막 handoff/status 커밋은 `docs: hand off backend quality gates` 메시지로 이 문서 뒤에 생성된다.

## 3. 구현된 동작

### 설정과 manifest

- 기본값은 `EMBEDDING_DIMENSIONS=1536`, `CHUNK_SIZE=900`, `CHUNK_OVERLAP=150`이다.
- manifest는 `CHROMA_PATH/index-manifest.json`에 schema version, provider, embedding model·dimension, chunk 설정, collection, raw posts SHA-256, topic rules SHA-256, indexed chunk count와 signature fingerprint를 기록한다.
- manifest는 strict Pydantic schema로 읽고 fingerprint 자체도 재검산한다.
- 호환성 reason은 `compatible`, `empty_index`, `index_unavailable`, `missing_manifest`, `invalid_manifest`, `settings_mismatch`, `content_mismatch`, `chunk_count_mismatch`로 구분한다.

### 인덱스 lifecycle

- 비어 있지 않은 인덱스는 `python -m backend.scripts.index --reset`으로만 전체 교체할 수 있다.
- 문서 청킹과 임베딩 차원 검증은 기존 collection reset 전에 수행한다.
- mutation 시작 전에 기존 manifest를 제거하고, 저장된 청크 수가 기대값과 정확히 일치할 때만 새 manifest를 원자적으로 기록한다.
- 설정·입력·OpenAI·Chroma 오류는 CLI exit 2로 정리하며 불완전한 인덱스를 정상으로 표시하지 않는다.

### API fail-closed 정책

- `/api/health`는 `ready`, `needs_configuration`, `needs_index`, `needs_reindex`, `unavailable`을 반환한다.
- `/api/chat`은 빈 인덱스나 호환성 불일치에 409, provider 설정 또는 저장소 문제에 503, OpenAI 호출 실패에 502를 반환한다.
- chat 차단은 answer provider 생성·호출 전에 수행한다.
- 주제·원본 cache는 semantic fingerprint를 사용하고, RAG service는 fingerprint와 manifest 생성 시각을 함께 key로 사용한다.
- Chroma collection handle은 영구 cache하지 않으므로 별도 인덱서가 collection을 reset해도 API가 새 collection ID를 다시 연다.

### 품질 gate와 CI

- `backend/pyproject.toml`은 `backend.app`, `backend.scripts` line coverage 85%를 강제한다.
- package `__init__.py`와 사용자 요청 범위 밖인 `backend/app/crawling/seboard.py`는 coverage에서 제외한다.
- `.github/workflows/quality.yml`은 PR과 `main` push에서 backend tests+coverage, Ruff, frontend tests, TypeScript, ESLint, production build를 실행한다.
- workflow는 read-only contents 권한과 concurrency cancellation을 사용한다.
- action major는 작성일의 공식 최신 major인 checkout v7, setup-python v6, setup-node v7을 사용한다.
- 로컬 대응 명령은 통과했지만 이 브랜치를 아직 push하지 않았으므로 GitHub Actions 원격 run은 검증하지 않았다.

## 4. 2026-07-15 실제 검증값

| 항목 | 결과 |
| --- | --- |
| 로컬 Python | 3.12.13 |
| backend pytest | 154 passed |
| product-code coverage | 91.42%, gate 85% 통과 |
| backend Ruff | 통과 |
| frontend Vitest | 3 files, 9 tests 통과 |
| frontend TypeScript | 깨끗한 `.next` 상태에서 통과 |
| frontend ESLint | 통과 |
| frontend production build | 통과, 정적 페이지 4개 |
| workflow YAML | `Quality`, backend/frontend jobs, read-only 권한 구조 확인 |
| 저장 게시글 | 50건 (`kumoh=50`, `seboard=0`) |
| 재인덱싱 | 84 chunks, exit 0 |
| manifest fingerprint | `9fe1fee46fbfba4fee7902c60ce544efcc7fbe46f432c81a62cf94709466a2b0` |
| health | `ready`, `compatible`, 84 chunks |
| compatibility/chat smoke | 16 tests 통과 |
| local RAG 평가 | 30/30, exit 0 |
| 평가 세부 | topic 30/30, grounded 30/30, latest-only 30/30, source-title 11/11 |
| 데이터 감사 | 50 posts, 3 issues, 의도된 exit 1 |

frontend 검사를 동시에 실행하면 `next build`가 `.next/types`를 교체하는 동안 standalone `tsc`가 파일을 읽어 경합할 수 있다. workflow는 test → typecheck → lint → build 순서로 실행하므로 이 경합이 없고, `.next`와 `tsconfig.tsbuildinfo`를 지운 깨끗한 상태의 typecheck도 별도로 통과했다.

독립 코드 리뷰에서 stale Chroma handle과 npm prefix 기반 typecheck 경로를 Important로 지적했다. 둘 다 수정했으며, 후속 리뷰에서 동일 fingerprint 재인덱싱 시 service cache가 남는 추가 경계를 찾아 manifest 생성 시각을 내부 세대 키로 반영했다. 실제 Chroma 두 handle을 사용하는 회귀 테스트는 reset 전후 fingerprint가 같고 generation이 다르며 새 service가 새 collection을 읽는지 검증한다.

## 5. 해결되지 않은 데이터·외부 상태

감사 경고는 숨기거나 임의 데이터로 해결하지 않았다.

| 경고 | 현재 상태 | 다음 조치 |
| --- | --- | --- |
| `missing_source=seboard` | 게시글 0건 | 운영자 서면 허가 또는 승인된 공식 API 확보 |
| `stale_topic=course_openings` | 최신 게시일 2025-08-07 | 공식 원문에서 실제 최신 개설강좌 공지 확인 |
| `empty_topic=graduation` | 게시글 0건 | 승인된 공식 소스 확보 또는 자료 부재 UX 결정 |

“주제별 최신”은 현재 저장 데이터 안에서의 최신이다. 따라서 `course_openings`처럼 저장 데이터 자체가 오래된 경우 날짜와 원문 링크를 계속 노출하고 중요한 학사 결정은 원문 재확인을 안내해야 한다.

## 6. 범위·보안 확인

- `backend/app/crawling/seboard.py`를 수정하지 않았다.
- `data/evaluation/questions.json`의 고정 기대값을 낮추거나 수정하지 않았다.
- Chroma DB, manifest, coverage 파일, 평가·감사 보고서는 `.gitignore` 대상이다.
- API key, password, bearer token은 커밋하거나 문서에 기록하지 않았다. 실제 비밀값은 `민감정보 제거됨`으로 취급한다.

최종 확인 명령:

```powershell
git diff 3c016de...HEAD -- backend/app/crawling/seboard.py
git diff 3c016de...HEAD -- data/evaluation/questions.json
rg -n -P "^(?:OPENAI_API_KEY|API_KEY|PASSWORD)=\S+|Bearer\s+[A-Za-z0-9]" .github backend docs README.md .env.example
```

앞의 두 diff는 비어 있어야 한다. secret scan은 빈 `.env.example` key나 보안 문서의 탐지 예시만 출력할 수 있으므로 값을 직접 검토한다.

## 7. 다음 권장 작업

1. 이 브랜치를 push하고 GitHub Actions의 backend/frontend 두 job을 실제 확인한 뒤 required check로 지정한다.
2. frontend 통합/E2E와 접근성 자동화를 추가한다. fetch 성공·409/503 오류·추천 질문 재질문·최근 공지와 390px/1280px 흐름을 포함한다.
3. request ID, 주제·출처·점수·지연시간을 민감정보 없이 기록하고 rate limit·provider timeout·운영 CORS를 강화한다.
4. Docker healthcheck/readiness, Chroma backup/restore와 데이터 변경 시 재인덱싱 runbook을 구현한다.
5. 외부 권한이 해결될 때만 SE 데이터 작업을 재개한다.

P0 데이터 최신성 검증과 원격 CI 확인 전에는 “운영 준비 완료”로 표시하지 않는다.

## 8. 전체 로컬 재검증 명령

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests --cov=backend.app --cov=backend.scripts --cov-config=backend/pyproject.toml --cov-report=term-missing
backend/.venv/Scripts/python.exe -m ruff check backend
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate
backend/.venv/Scripts/python.exe -m backend.scripts.audit_data
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
git diff --check
```

현재 예상 exit은 평가 0, 감사 1이다. 감사 exit 1은 위 3개 데이터 품질 경고가 존재한다는 뜻이며 test 실패로 오인하지 않는다.
