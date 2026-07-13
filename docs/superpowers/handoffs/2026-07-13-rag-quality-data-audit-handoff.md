# RAG 품질·데이터 감사 구현 인수인계

작성일: 2026-07-13

상태: 사용자 요청으로 구현 중단, 재개 준비 완료

재개 우선순위: Task 1 코드 품질 리뷰 재실행 → Task 2 시작

## 1. 재개 진입점

다음 작업자는 새 브랜치나 새 worktree를 만들지 말고 아래 기존 worktree에서 이어간다.

```powershell
Set-Location 'C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot\.worktrees\rag-quality-hardening'
git branch --show-current
git status --short
git log -4 --oneline
```

예상 상태:

| 항목 | 값 |
| --- | --- |
| 작업 브랜치 | `codex/rag-quality-hardening` |
| 현재 기능 HEAD | `4093c94 feat: validate retrieval evidence policy` |
| Task 1 기준 커밋 | `93dd6d7 docs: plan rag quality and data audit` |
| 루트 worktree | `main`, `25bd63b` |
| 원격 기준 | `origin/main`, `25bd63b` |
| push/PR | 아직 수행하지 않음 |

첫 작업은 아래 범위의 **코드 품질 리뷰를 새 검토자로 다시 실행하는 것**이다.

```powershell
git diff --stat 93dd6d7..4093c94
git diff 93dd6d7..4093c94
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_topic_rules.py backend/tests/test_topic_classifier.py backend/tests/test_recommendations.py -q
backend/.venv/Scripts/python.exe -m ruff check backend/app/topic_rules.py backend/tests/test_topic_rules.py
```

Task 1 명세 리뷰는 통과했지만 코드 품질 리뷰는 사용자 중단 요청으로 종료되어 결과가 없다. 따라서 Task 1을 최종 승인 처리하거나 Task 2로 넘어가기 전에 품질 리뷰를 다시 수행해야 한다. Critical/Important 지적이 나오면 같은 Task 1 범위에서 테스트 우선으로 수정하고 재검토한다.

## 2. 기준 문서

- 설계: [`../specs/2026-07-13-rag-quality-data-audit-design.md`](../specs/2026-07-13-rag-quality-data-audit-design.md)
- 전체 구현 계획: [`../plans/2026-07-13-rag-quality-data-audit-implementation.md`](../plans/2026-07-13-rag-quality-data-audit-implementation.md)
- 프로젝트 전체 상태: [`../../PROJECT_STATUS.md`](../../PROJECT_STATUS.md)
- 이전 자동 평가 인수인계: [`2026-07-12-rag-evaluation-handoff.md`](2026-07-12-rag-evaluation-handoff.md)

구현 계획은 Task 1~9의 파일 범위, RED 테스트, 최소 구현, GREEN 명령, 커밋 메시지를 모두 포함한다. 다음 작업자는 계획의 Task 본문을 작업자에게 직접 제공하고, 각 Task마다 구현 → 명세 리뷰 → 코드 품질 리뷰 순서를 유지한다.

## 3. 핵심 결정 3개

1. 기존 `data/evaluation/questions.json` 30문항 기대값을 약화하지 않고 local 평가를 25/30에서 30/30으로 개선한다.
2. 최신성은 `topic_key`별 최신 1건 정책을 유지하되 질문의 연도·학기 충돌을 거절하고, 제목 marker·동의어가 질문 근거와 연결될 때만 grounded로 인정한다.
3. 부분 수집 결과는 운영 원본을 덮어쓰지 않고 후보 경로에 저장하며, 데이터 감사와 공식 사이트 live 최신성 검증을 로컬 구현과 외부 검증으로 분리한다.

## 4. 이번 세션에서 완료한 작업

### 설계와 계획

| 커밋 | 내용 |
| --- | --- |
| `5bfd23b` | 기간 충돌, 제목 근거, 일반 최신 공지, 부분 수집, 데이터 감사 설계 |
| `93dd6d7` | 9개 Task와 TDD·검토·검증 명령을 포함한 상세 구현 계획 |

설계에서 확정한 정책:

- `topic_key`별 `is_latest_topic=true` 정책 유지
- 질문의 연도·학기와 문서 제목이 충돌하면 근거 거절
- 제목 evidence marker는 질문 표현 또는 alias와 연결되어야 함
- 일반 “최근 학과 공지”는 게시일 기준 가장 최신 URL을 우선
- false-positive 3건과 false-negative 2건을 기대값 변경 없이 수정
- 부분 수집 후보 경로와 운영 원본 분리
- 감사 JSON·Markdown과 평가 보고서가 공용 원자적 writer 사용
- 공식 사이트 최신성·실제 양쪽 소스 수집은 외부 검증 대기로 유지

### 격리 worktree와 기준선

- `.worktrees/`의 ignore를 확인하고 전용 worktree를 생성했다.
- `backend/.venv`에 고정 requirements를 설치했다.
- `frontend/node_modules`를 `npm ci`로 설치했다.
- local Chroma 인덱스를 게시글 46건·청크 79개로 재생성했다.
- 생성된 venv, node_modules, `.next`, Chroma, 평가 보고서는 Git 제외 대상이다.

기준선 검증:

| 검증 | 결과 |
| --- | --- |
| backend pytest, Task 1 전 | 57 passed |
| backend Ruff | `All checks passed!` |
| frontend Vitest | 3 files, 9 tests passed |
| frontend ESLint | exit 0 |
| Next.js production build | exit 0, 정적 페이지 4개 |
| 인덱싱 | 46 posts, 79 chunks, exit 0 |
| 실제 local 평가 | 30건 중 25건 통과, exit 1 |

비차단 기준선 경고:

- Vitest 실행 시 Vite CJS Node API deprecation 경고가 있다.
- `npm ci` 후 audit는 5건(보통 3, 높음 1, 치명적 1)을 보고했다. 자동 수정이나 breaking upgrade는 수행하지 않았다.

### Task 1 — 검색 정책 설정 모델과 엄격한 로딩

커밋: `4093c94 feat: validate retrieval evidence policy`

변경 파일:

- `backend/app/topic_rules.py`
- `backend/tests/test_topic_rules.py`

구현 내용:

- immutable `RetrievalPolicy`
- `TopicRule.evidence_markers`
- `TopicCatalog.retrieval_policy`
- 문자열 배열의 빈 값·중복 검증
- alias group 최소 2개 표현 검증
- 중복 topic key 거절
- 기존 `rule_for()`·`classify()`와 positional 생성자 호환 유지

TDD 증거:

- RED: `test_topic_rules.py` 실행 결과 2 passed, 3 failed
  - `evidence_markers` 부재 `AttributeError`
  - 단일 alias group이 거절되지 않음
  - 중복 topic key가 거절되지 않음
- GREEN: topic rules/classifier/recommendations 9 passed
- Task 1 반영 후 전체 backend: 60 passed
- Ruff: `All checks passed!`
- 명세 리뷰: `✅ Spec compliant`
- 코드 품질 리뷰: 실행 중 사용자 요청으로 종료, **재실행 필요**

## 5. 활성 품질 실패 5건

현재 normative 30문항은 변경하지 않았다. 실제 평가는 25/30, quality exit 1이다.

| 유형 | case ID | 필요한 동작 |
| --- | --- | --- |
| false-positive | `registration-period` | 질문 조건과 맞지 않는 최신 주제 문서를 grounded로 채택하지 않음 |
| false-positive | `capstone-second-semester` | 2학기 질문에 1학기 문서를 근거로 사용하지 않음 |
| false-positive | `scholarship-apply` | 신청 근거가 없는 문서를 장학금 신청 답변 근거로 사용하지 않음 |
| false-negative | `career-recruitment` | “채용” 질문이 최신 “초빙” 제목을 동의어 근거로 찾음 |
| false-negative | `general-recent-department` | 일반 최근 공지에서 게시일이 가장 최신인 학과 URL을 선택함 |

기준 metric:

- topic: 30/30
- grounded: 25/30
- latest-only: 28/30
- source-title: 10/11

## 6. 남은 작업

### 즉시 재개

1. Task 1 코드 품질 리뷰를 새 검토자로 재실행한다.
2. Critical/Important가 없으면 Task 1 작업자를 종료하고 Task 2를 시작한다.
3. 이 문서의 진행 기록에 리뷰 결과와 후속 커밋을 추가한다.

### 구현 계획 Task 2~9

| Task | 상태 | 목적 |
| --- | --- | --- |
| Task 2 질문 의도 분석 | 미시작 | 연도·학기·최근성·alias·distinctive term 추출 |
| Task 3 기간·제목 근거 정책 | 미시작 | 기간 충돌과 제목 marker/특징어 근거를 순수 함수로 판정 |
| Task 4 RAG 연결과 실패 5건 회귀 | 미시작 | 실제 검색·필터·rerank에 정책 연결, 30문항 기대값 유지 |
| Task 5 부분 수집 후보 분리 | 미시작 | 부분 성공 데이터를 `data/raw/candidates/`에만 저장 |
| Task 6 공용 원자적 보고서 writer | 미시작 | 평가·감사의 쌍 보고서 교체/rollback 계약 통합 |
| Task 7 데이터 감사 순수 계층 | 미시작 | source/topic 최신성·누락·분류 경고 집계 |
| Task 8 데이터 감사 CLI | 미시작 | JSON·Markdown, exit 0/1/2, 민감정보·본문·절대경로 제외 |
| Task 9 전체 검증·운영 문서 | 미시작 | 재인덱싱, 실제 30/30, 전체 회귀, 상태·인수인계 완료 |

각 Task의 정확한 테스트와 구현 계약은 전체 구현 계획을 따른다. Task 간 의존성이 있으므로 순서를 바꾸지 않는다.

## 7. 외부 검증 대기

다음은 로컬 코드만으로 완료로 표시하면 안 된다.

- 학과·SE 공식 사이트의 live crawl 성공
- 공식 원문 기준 최신 게시일과 source URL 수동 대조
- `course_openings`의 현재 최신 자료 2025-08-07이 실제 최신인지 확인
- 실제 운영 OpenAI provider 임계값 재평가
- GitHub CI가 아직 없으므로 원격 필수 검사 구성

부분 수집 기능이 구현되더라도 `--allow-partial` 결과를 운영 `data/raw/posts.json`에 바로 승격하지 않는다.

## 8. 재개 직후 검증 체크리스트

```powershell
git status --short
git branch --show-current
git diff --check
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
backend/.venv/Scripts/python.exe -m ruff check backend
```

- [ ] branch가 `codex/rag-quality-hardening`이다.
- [ ] 계획 밖 추적 변경이 없다.
- [ ] backend 60개 테스트가 통과한다.
- [ ] Ruff가 통과한다.
- [ ] Task 1 품질 리뷰를 다시 수행했다.
- [ ] Task 2는 새 failing test로 시작한다.

## 9. 최종 완료 조건

- normative 30문항 파일이 `main` 대비 변경되지 않음
- false-positive 3건은 grounded=false이고 provider answer 미호출
- false-negative 2건은 최신 URL·게시일을 포함해 grounded=true
- 실제 local 평가 30/30, exit 0
- 부분 수집이 운영 원본을 덮어쓰지 않음
- 감사 JSON·Markdown 생성, 본문·비밀값·로컬 절대경로 미포함
- backend pytest·Ruff와 frontend test·typecheck·lint·build 모두 통과
- 로컬 완료와 공식 사이트 외부 검증 대기를 문서에서 구분
- 기능 브랜치 push와 PR 리뷰 후에만 main 병합

## 10. 진행 기록 템플릿

각 Task 또는 리뷰가 끝날 때 아래 형식으로 이 문서 하단에 추가한다.

```markdown
### YYYY-MM-DD — Task N / review

- RED: 명령, 실패 수, 기대한 실패 이유
- GREEN: 구현 파일, 통과 명령, 정확한 테스트 수
- Review: 명세 결과, 품질 결과, 수정 여부
- Commit: hash와 메시지
- Generated reports: 경로와 ignore 확인
- Next: 다음 시작 테스트 또는 외부 검증
```

민감정보는 기록하지 않는다. `.env`, API key, password, bearer token, 로컬 비밀 경로가 발견되면 `민감정보 제거됨`으로 대체한다.
