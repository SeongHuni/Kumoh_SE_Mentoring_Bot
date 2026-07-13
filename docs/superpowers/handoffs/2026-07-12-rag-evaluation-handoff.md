# SE Mentor Bot 자동 평가 작업 인수인계

> 갱신 시점: 2026-07-13, Task 1~6 완료·원격 main 통합 회귀 수정·PR 게시 전

## 작업 목표

현재 Chroma 인덱스와 RAG 경로를 local provider로 실행해 topic·grounded·latest-only·source-title을 검사하는 자동 평가 CLI와 30개 평가셋을 만들고, 실제 품질 간극을 반복 측정할 수 있게 한다.

## 현재 저장소 상태

- 격리 작업 트리: `C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot\.worktrees\topic-latest`
- 작업 브랜치: `codex/rag-evaluation`
- 로컬 `main`과 `origin/main`: `8473c78 Ignore evaluation reports and export script entrypoint`.
- `origin/main`은 `2a0b447` merge commit으로 기능 브랜치에 통합했다.
- 이번 자동 평가 변경은 아직 `main`에 병합하거나 원격에 푸시하지 않았다.
- Task 6 검증·리뷰 기록 커밋: `742436b docs: finalize rag evaluation handoff`.
- 원격 통합 회귀 수정은 검증 뒤 별도 fix 커밋으로 묶는다.
- 생성된 `chroma_db`와 `data/evaluation/reports/`는 Git 제외 상태다.

## 확정된 설계

- 선택안: 비용 없는 local End-to-End 평가
- 순수 평가 계층: `backend/app/evaluation.py`
- CLI wiring: `backend/scripts/evaluate.py`
- 평가 데이터: `data/evaluation/questions.json`, 최소 30개
- 보고서: `data/evaluation/reports/latest.json`, `latest.md`; Git 제외
- 종료 코드: 성공 0, 평가 실패 1, 실행 오류 2
- 기본 provider: `local`; `configured`는 명시적으로 선택
- 런타임 API 응답 스키마는 변경하지 않는다.

설계 문서:

- `docs/superpowers/specs/2026-07-12-rag-evaluation-design.md`
- `docs/superpowers/plans/2026-07-12-rag-evaluation-implementation.md`

## 진행도

| 단계 | 상태 | 근거 |
| --- | --- | --- |
| 코드·문서 현황 재검토 | 완료 | main, PROJECT_STATUS, RAG·provider·data interface 확인 |
| 접근안 비교 | 완료 | End-to-End, retrieval-only, provider matrix 비교 |
| 사용자 설계 승인 | 완료 | 사용자가 `승인` 응답 |
| 설계 문서 작성·커밋 | 완료 | `ebb7bbb docs: design automated rag evaluation workflow` |
| 상세 구현 계획 | 완료 | Task 1~6, RED/GREEN·커밋·진행 기록 단계와 self-review 완료 |
| Task 1~3 평가 계층·CLI | 완료 | strict schema, 4개 check, JSON/Markdown, exit 0/1/2, 보고서 트랜잭션 검증 |
| Task 4 30개 baseline | 완료 | exact ID·분포·기대값 회귀 계약, 실제 평가 25/30 |
| Task 5 운영 문서 | 완료 | README·operations·PROJECT_STATUS·handoff에 실행법과 측정 결과 반영 |
| Task 6 전체 검증 | 완료 | backend/frontend/실평가/보안·Git hygiene 통과, quality exit 1 재현 |
| 전체 구현 독립 리뷰 | 완료 | 백엔드와 데이터·문서·보안 분리 리뷰 모두 Critical/Important/Minor 없음, Approved |
| PR 통합 preflight | 완료 | origin/main 병합, eager import RuntimeWarning RED→GREEN, 전체 회귀 통과 |

## 커밋 목록

1. `3124680 feat: validate rag evaluation cases`
2. `c0ce5bd fix: enforce strict evaluation case schema`
3. `6ff35e7 feat: evaluate rag quality expectations`
4. `eb748fd fix: harden rag evaluation execution and reports`
5. `3b02794 feat: add rag evaluation cli`
6. `7e36f2f fix: align rag evaluation cli contract`
7. `b75db4b fix: make rag report writes transactional`
8. `f8ab6a4 fix: preserve failed rollback backups`
9. `c63b2ae test: add structured rag evaluation baseline`
10. `230ef9d test: lock rag evaluation baseline contract`
11. `f372101 test: pin exact evaluation questions and categories`
12. `ce2119f docs: document automated rag evaluation`
13. `742436b docs: finalize rag evaluation handoff`
14. `2a0b447 Merge remote-tracking branch 'origin/main' into codex/rag-evaluation`
15. `(현재 수정 커밋) fix: avoid eager evaluation script import`

## 다음 작업자 즉시 수행 항목

1. 현재 수정 커밋을 만든 뒤 `codex/rag-evaluation`을 원격에 push한다.
2. `main` 대상 Draft PR을 생성하고 URL·검증 결과를 기록한다.
3. PR 검토·병합 전까지 worktree를 삭제하지 않는다.
4. 통합 후 다음 구현은 평가 실패 5건을 재현하는 집중 RAG 결함 수정 계획부터 시작한다.
5. 그다음 P0-2 공식 데이터 재수집과 30개 baseline 원문 재검토를 진행한다.

## TDD 진행 기록 형식

각 작업 뒤 이 문서에 다음을 추가한다.

- 마지막 RED 테스트와 예상 실패 이유
- GREEN 구현 파일과 통과 명령
- 전체 회귀 결과
- 마지막 커밋 hash
- 다음 시작 테스트

## 알려진 주의사항

- `data/evaluation/questions.json`은 exact 30개 구조화 baseline이며 데이터 재수집 시 기대값을 공식 원문과 다시 검토해야 한다.
- 현재 데이터에서 `course_openings` 최신 게시일은 2025-08-07이다.
- 실제 실패 5건: `registration-period`, `capstone-second-semester`, `career-recruitment`, `scholarship-apply`, `general-recent-department`.
- false-positive 3건은 `registration-period`, `capstone-second-semester`, `scholarship-apply`이고, 나머지 2건은 false-negative다.
- 자동 평가 도구는 완료됐지만 RAG 품질은 25/30이므로 완료로 표시하지 않는다.
- OpenAI, live crawler, CI는 이번 구현 범위 밖이다.
- `.env`, API key, `chroma_db`, 평가 생성 보고서는 커밋하지 않는다.

### Task 1 — EvaluationCase와 loader

- RED: evaluation module 부재로 test collection 실패
- GREEN: 유효 입력, 중복 id, kebab-case, grounded/source 모순 테스트 통과
- 다음 시작점: topic·grounded·latest source 평가 실패 테스트

### Task 1 review fix — strict schema

- RED: unknown field 1건과 non-boolean `expected_grounded` 2건이 permissive Pydantic 동작으로 실패(총 3 failures)
- GREEN: strict schema 적용 후 evaluation 테스트 10개 통과
- 커밋: `fix: enforce strict evaluation case schema`
- 작업 중단점: Task 1 strict-schema review fix 완료, Task 2 미시작
- 다음 작업자 시작점: Task 2 evaluator/result/report symbol import RED 테스트

### Task 2 — 순수 evaluator와 보고서

- RED: evaluator/result/report symbol import 실패
- GREEN: topic·grounded·latest-only·source-title·metric·Markdown 테스트 통과
- 전체 회귀: backend pytest 42 passed, Ruff `All checks passed!`
- 다음 시작점: CLI 성공 0·평가 실패 1·실행 오류 2 테스트

### Task 2 review fix — 실행 preflight와 Markdown hardening

- RED A: valid case 뒤 unknown topic에서 `ask_calls == 1`로 선검증 부작용 재현
- GREEN A: case iterable materialize 후 전체 topic preflight, generator 입력과 callback 0회 보장
- RED B: newline 뒤 `# injected-question`이 raw Markdown heading으로 렌더링됨
- GREEN B: 동적 metadata·case·source·failure whitespace 정규화와 Markdown inline escape 적용
- Characterization C: general은 다른 topic의 latest URL 허용, course_openings는 동일 URL 거부(첫 실행 통과)
- 전체 회귀: evaluation pytest 19 passed, backend pytest 45 passed, Ruff `All checks passed!`, `git diff --check` 통과
- 다음 시작점: CLI 성공 0·평가 실패 1·실행 오류 2 테스트

### Task 3 — 평가 CLI와 원자적 보고서

- RED import failure: `backend.scripts.evaluate` 미노출로 collection import 실패
- GREEN exit 0/1/2, minimum cases, empty index: CLI 종료코드·최소 케이스·빈 인덱스 테스트 완료
- atomic latest.json/latest.md and ignore confirmation: `NamedTemporaryFile` 기반 원자적 기록과 `data/evaluation/reports/` ignore 확인 완료
- exact full backend count: 50 passed
- next: committed dataset 30 cases/category distribution RED

### Task 3 quality fix — 보고서 쌍 트랜잭션

- RED A: `write_reports`의 `OSError("disk full")`가 `main` 밖으로 전파되어 exit 2 계약 실패
- RED B: 두 번째 보고서 replace 실패 시 새 JSON·이전 Markdown 혼합 상태와 `.tmp` 잔존 위험 재현
- GREEN: 두 내용을 먼저 staging하고 기존 쌍을 백업한 뒤 함께 commit하며, 실패 시 두 파일 rollback·임시/백업 정리·`OSError`/롤백 `RuntimeError` exit 2 처리 완료
- 검증: evaluate CLI 8 passed, 전체 backend 53 passed, Ruff `All checks passed!`
- next: committed dataset 30 cases/category distribution RED

### Task 3 quality fix — rollback-backup preservation

- RED: 두 번째 report commit 실패 + JSON backup restore 실패 시, 기존 cleanup이 실패한 `.bak`까지 삭제하는 회귀를 `test_main_preserves_failed_rollback_backup_for_manual_recovery`로 재현
- GREEN: `RollbackFailure`로 실패한 복구 대상의 backup 경로를 보존 목록에 실어 cleanup에서 제외하고, RuntimeError/stderr에 보존된 backup 경로를 노출
- 검증: focused `backend/tests/test_evaluate_script.py` 9 passed, 전체 `backend/tests` 54 passed, Ruff `All checks passed!`, `backend.scripts.evaluate --help` 정상 출력, `git diff --check` 통과
- 작업 중단점: rollback-backup fix 완료, 다음 작업은 Task 4 dataset RED

### Task 4 — 30개 baseline

- RED reason: `backend/tests/test_evaluation_dataset.py`가 현재 8개짜리 `data/evaluation/questions.json`을 읽는 순간 `EvaluationCase` 필수 필드(`id`, `expected_topic_key`, `expected_grounded`, `expected_latest_only`) 누락으로 `ValidationError`를 발생시켜야 했고, 실제로 그렇게 실패했다.
- exact case count and category counts: 총 30개, `개설강좌` 4, `수강신청` 5, `캡스톤` 4, `진로·취업` 4, `장학금` 4, `졸업요건` 3, `일반 공지` 3, `범위 밖` 3.
- dataset/full test and Ruff results: `backend/tests/test_evaluation_dataset.py` 1 passed, `backend/tests` 55 passed, `backend/.venv/Scripts/python -m ruff check backend` → `All checks passed!`
- exact index output: `게시글 46건, 청크 79개 인덱싱 완료 (provider=local, embedding=local-hash-embedding-v1)`
- exact evaluation process exit code: `backend/.venv/Scripts/python -m backend.scripts.evaluate` → exit code `1`
- report summary total/passed/failed and metrics:
  - summary: `total=30`, `passed=25`, `failed=5`
  - topic: `{"passed": 30, "total": 30, "rate": 1.0}`
  - grounded: `{"passed": 25, "total": 30, "rate": 0.8333}`
  - latest_only: `{"passed": 28, "total": 30, "rate": 0.9333}`
  - source_title: `{"passed": 10, "total": 11, "rate": 0.9091}`
- every failed case_id: `registration-period`, `capstone-second-semester`, `career-recruitment`, `scholarship-apply`, `general-recent-department`
- generated report paths and ignored status: `data/evaluation/reports/latest.json`, `data/evaluation/reports/latest.md` 생성됨; 둘 다 Git 제외 대상이라 커밋하지 않음.
- 다음 시작점: README·operations·PROJECT_STATUS에 이번 baseline/평가 결과 반영

### Task 4 quality fix — baseline 계약 고정

- 리뷰 위험: 기존 테스트의 `>= 30`과 카테고리별 최소 건수만으로는 canonical ID 교체·순서 변경·추가 케이스와 grounded/source-title 기대값 약화를 감지하지 못할 수 있었다.
- 보강: 정확한 30개 ID·질문·카테고리와 순서, 카테고리별 정확한 건수와 topic, grounded=true ID 집합, source-title fragment를 회귀 계약으로 고정했다. 평가에 쓰이지 않는 운영 메모 `notes`만 데이터 갱신 시 합리적으로 수정할 수 있게 중복 고정하지 않았다.
- 검증: `backend/tests/test_evaluation_dataset.py` 2 passed, 전체 `backend/tests` 56 passed, Ruff `All checks passed!`.
- 다음 시작점: Task 5 README·operations·PROJECT_STATUS·handoff 문서화

### Task 5 — 운영 문서와 프로젝트 상태

- README 검증 명령에 `backend/.venv/Scripts/python -m backend.scripts.evaluate`를 추가하고 local 기본값, 보고서 경로, exit 1/2 의미를 기록했다.
- `docs/rag/operations-evaluation.md`에 재인덱싱부터 자동 평가까지의 명령, provider·보고서·exit code 정책, 5개 CLI 인자 표를 추가했다.
- `docs/PROJECT_STATUS.md`에서 P1-1 도구 구현을 완료로 표시하되 RAG 품질은 25/30으로 미완료임을 분리했다.
- 실제 보고서: `data/evaluation/reports/latest.json`, `data/evaluation/reports/latest.md`; Git 제외 상태이며 커밋 대상이 아니다.
- 알려진 실패: `registration-period`, `capstone-second-semester`, `scholarship-apply` false-positive; `career-recruitment`, `general-recent-department` false-negative.
- 문서 검증: `git diff --check` exit 0.
- 다음 시작점: Task 6 전체 backend/frontend 회귀, 실제 평가·민감정보 점검, 전체 구현 독립 리뷰

### Task 6 — 전체 회귀와 실제 평가 검증

- backend: `backend/.venv/Scripts/python -m pytest backend/tests -q` → 56 passed; `backend/.venv/Scripts/python -m ruff check backend` → `All checks passed!`.
- frontend: Vitest 3 files·9 tests passed, TypeScript `--noEmit --incremental false` exit 0, ESLint exit 0.
- production build: Next.js 15.5.20 compile 성공, 정적 페이지 4개 생성. build가 자동 변경한 `frontend/next-env.d.ts`는 저장소 버전으로 복원했다.
- 실제 평가: `backend/.venv/Scripts/python -m backend.scripts.evaluate` → quality exit 1, `total=30`, `passed=25`, `failed=5`.
- metric: topic `30/30`, grounded `25/30`, latest-only `28/30`, source-title `10/11`.
- 실패 ID: `registration-period`, `capstone-second-semester`, `career-recruitment`, `scholarship-apply`, `general-recent-department`.
- 보고서 구조: result에는 case/question/category/topic/grounded/source/check/failure/pass만, source에는 title/url/source/published_at/score만 존재하며 answer·body·content·post body 필드는 없다.
- 보안 검사: API key·password·secret·bearer·OpenAI key·provider/path 환경값 패턴 0건.
- Git hygiene: `latest.json`, `latest.md` 모두 `.gitignore`의 `data/evaluation/reports/` 규칙 적용; `git diff --check` 통과; 검증 직후 작업 트리 clean.
- 설계 완료 조건: 30개 구조화 case, local 기본, 4개 check, JSON/Markdown, exit 0/1/2, 트랜잭션 보고서 교체, 민감정보 제외, runtime API 무변경, 문서화 조건을 모두 충족했다.
- 비차단 경고: Vitest에서 Vite CJS Node API deprecation 경고가 유지된다. P2-6 의존성 정리에서 재평가한다.
- 다음 시작점: 사용자의 브랜치 통합 방식 선택

### Task 6 final review — 승인

- 백엔드 집중 리뷰: `backend/app/evaluation.py`, `backend/scripts/evaluate.py`의 4개 check, local/minimum/limit/exit 계약, 보고서 쌍 트랜잭션·rollback·backup 보존을 재검토했고 Critical/Important/Minor 없이 Approved.
- 데이터·문서·보안 집중 리뷰: exact 30 baseline, 25/30과 실패 5개 ID, report ignore·민감정보 제외, 문서의 명령·exit·브랜치·다음 작업 일관성을 재검토했고 Critical/Important/Minor 없이 Approved.
- 이전 Task 1~5의 명세·품질 리뷰 지적은 모두 수정 후 재승인됐다.
- 구현 범위 완료 판정: 자동 평가 도구와 운영 문서는 완료. 실제 RAG 품질은 25/30으로 별도 후속 작업이며 완료가 아니다.
- 통합 상태: 사용자가 Draft PR 진행을 승인했으며, origin/main 동기화 회귀 수정·재검증 뒤 push한다.

### PR preflight — origin/main 통합 회귀 수정

- 원격 변경: `8473c78`이 평가 보고서 ignore와 함께 `backend/scripts/__init__.py`에서 존재하지 않던 `evaluate` submodule을 두 번 eager import했다.
- root cause: 원격 main 단독으로 `import backend.scripts` 시 순환 ImportError가 발생했고, 기능 브랜치 통합 후에는 `python -m backend.scripts.evaluate --help`가 runpy RuntimeWarning을 출력했다.
- RED: `test_module_help_does_not_emit_runtime_warning`이 stderr의 `RuntimeWarning`을 감지해 실패했다.
- GREEN: package 초기화의 eager import를 제거했다. 기존 `from backend.scripts import evaluate`는 Python의 submodule import로 유지된다.
- 검증: backend 57 passed, Ruff 통과, CLI help exit 0·RuntimeWarning 없음, 실제 평가는 기존과 같은 quality exit 1과 25/30.
- frontend 재검증: Vitest 9 passed, TypeScript·ESLint exit 0, Next.js build 정적 페이지 4개 생성. 자동 변경된 `next-env.d.ts`는 저장소 버전으로 복원했다.
- 다음 시작점: fix 커밋 후 원격 push와 Draft PR 생성
