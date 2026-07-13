# SE Mentor Bot 프로젝트 상태와 다음 작업

> 기준일: 2026-07-13
> 기준 브랜치: `main`
> 자동 평가 통합 커밋: `6334bdc Merge pull request #2 from SeongHuni/codex/rag-evaluation`
> 기존 기능 통합 커밋: `8dc3078 Merge branch 'codex/topic-latest'`

이 문서는 프로젝트의 현재 진행도, 남은 위험, 개선 TODO, 단계별 검증 기준을 한곳에서 관리하는 운영 기준 문서다. 자동 평가 구현 이력은 [`superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md`](superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md), RAG 설계는 [`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md)를 참고한다.

## 1. 현재 결론

- 계획된 **주제별 최신 RAG와 추천 UX 기능은 구현·검증 완료** 상태다.
- 자동 평가 CLI와 30개 구조화 baseline은 PR #2로 `main`에 통합됐고, JSON·Markdown 보고서와 exit 0/1/2 계약도 병합 후 재검증됐다.
- 실제 local 평가는 30개 중 25개만 통과했다. **평가 도구 완료와 RAG 품질 완료는 별개**이며, 아래 5개 실패를 해결하기 전에는 품질 완료로 판단하지 않는다.
- 로컬 프로토타입은 실행 가능하지만, **실데이터 최신성·SE 게시판 수집·5개 RAG 품질 결함·운영 안전성은 추가 검증이 필요**하다.
- 따라서 현재 단계는 `품질 자동화 도구 완료 → 측정된 RAG 결함 개선`이며, 파일럿 또는 운영 완료로 판단하지 않는다.

현재 활성 품질 작업:

- P1-1 자동 평가 CLI와 30개 평가셋: 구현 완료
- 설계: `docs/superpowers/specs/2026-07-12-rag-evaluation-design.md`
- 진행 인수인계: `docs/superpowers/handoffs/2026-07-12-rag-evaluation-handoff.md`
- 측정 결과: `total=30`, `passed=25`, `failed=5`; topic 100%, grounded 83.33%, latest-only 93.33%, source-title 90.91%
- 다음 권장 작업: 실패 5건을 false-positive/false-negative로 나눈 집중 RAG 결함 수정 계획을 세운 뒤 P0-2 공식 데이터 재수집과 baseline 재검토 수행

## 2. 단계별 진행도

| 영역 | 상태 | 완료 근거 | 다음 조건 |
| --- | --- | --- | --- |
| 요구사항·설계 | 완료 | 최신성·추천 UX와 자동 평가 Task 1~6 설계·계획 존재 | 정책 변경 시 설계와 이 문서 동시 갱신 |
| 백엔드 RAG | 완료 | 주제 분류, 최신성 계산, Chroma filter, 추천 질문·최근 공지 구현 | 실데이터 평가와 미검증 provider 보강 |
| 프론트엔드 | 완료 | A 집중형 채팅, 출처·추천 chip·최근 공지, 모바일 대응 | 페이지 통합/E2E 및 접근성 자동화 |
| 단위·컴포넌트 테스트 | 통과 | backend 57개, frontend 9개 | 커버리지 사각지대 해소 |
| 자동 평가 도구 | 완료 | 30개 case, 4개 check, JSON·Markdown 보고서, exit 0/1/2 검증 | 실패 5건 수정 후 품질 재측정 |
| 문서·운영 절차 | 완료 | README와 RAG 운영 문서에 재인덱싱·자동 평가 절차 존재 | 데이터/환경 변경 때 현행화 |
| 데이터 준비 | 부분 완료 | 학과 게시글 46건, 79청크 인덱싱 확인 | 양쪽 공식 소스 재수집과 최신성 감사 |
| 브랜치 통합 | 완료 | PR #2 ready 전환·`6334bdc`로 main 병합·병합 후 전체 회귀 | 후속 기능은 새 브랜치와 PR로 통합 |
| 파일럿 준비 | 차단 | 자동 평가 5건 실패·실수집·주제 세분화 검증 부족 | P0·P1 TODO 완료 |
| 운영 준비 | 미착수 | CI, 관측성, rate limit, backup 기준 미완성 | 운영 검증 매트릭스 충족 |

현재 실행·브랜치 스냅샷:

| 항목 | 값 |
| --- | --- |
| 기능 통합 커밋 | `8dc3078 Merge branch 'codex/topic-latest'` |
| 기능 구현 기준 HEAD | `8a02351 docs: finalize topic latest handoff` |
| 자동 평가 통합 | PR #2, merge commit `6334bdc` |
| provider | `local` |
| embedding | `local-hash-embedding-v1`, 1,536차원 |
| answer | `local-extractive-answer-v1` |
| retrieval | `top_k=5`, `min_score=0.09` |
| 데이터·인덱스 | 게시글 46건, 청크 79개 |
| 자동 평가 | 30건 중 25건 통과, quality exit 1 |
| 평가 보고서 | `data/evaluation/reports/latest.json`, `latest.md`(Git 제외) |

## 3. 구현된 기능

### 데이터와 최신성

- `data/topic_rules.json`에서 주제 키·표시명·키워드·추천 질문 관리
- 제목과 본문을 규칙으로 분류하고 일치하지 않으면 `general` 사용
- 유효한 `published_at` 우선, 누락·파싱 실패 시 `crawled_at` fallback
- 같은 주제의 최신 게시글만 `is_latest_topic=true`로 표시
- 원본 또는 규칙 변경 후 `backend/.venv/Scripts/python -m backend.scripts.index --reset` 수행

### 검색과 답변

- 구체 주제: `topic_key`와 `is_latest_topic=true`를 Chroma `where`에 함께 적용
- 일반 질문: 모든 주제의 최신 게시글만 검색
- 제목 일치 재정렬, 절대·상대 점수 필터, 근거 부족 시 provider 미호출
- API 호환 필드 `answer`, `sources`, `grounded` 유지
- 후속 필드 `suggested_questions`, `recent_notices` 추가

### 프론트엔드

- 답변 → 출처 → 추천 질문 → 최근 공지 순서의 읽기 흐름
- 추천 질문 클릭 시 기존 질문 전송 경로 재사용
- 답변 줄바꿈·긴 문자열 보존, 공지 원문 링크와 주제·게시일 표시
- 720px 이하에서 추천 chip 내부 가로 스크롤, 본문과 공지 카드 가로 넘침 방지
- API 오류·로딩·빈 후속 정보 처리

## 4. 데이터 상태와 품질 위험

현재 `data/raw/posts.json` 46건을 규칙으로 분류한 결과다.

| 주제 | 게시글 수 | 현재 최신 게시일 | 현재 최신 제목 |
| --- | ---: | --- | --- |
| `general` | 14 | 2026-06-17 | 2026학년도 AX 기반 역량 강화 프로젝트 공모 기간 연장 |
| `career` | 13 | 2026-06-30 | 소프트웨어전공 전임교원 초빙 공개강의 심사 공고 |
| `registration` | 12 | 2026-06-16 | 여름계절수업 조기취업자 출석인정신청 안내 |
| `scholarship` | 5 | 2026-06-17 | 방산AI인재양성부트캠프 설명회 안내 |
| `capstone` | 1 | 2026-03-19 | 2026학년도 1학기 캡스톤 디자인 운영 계획 |
| `course_openings` | 1 | 2025-08-07 | 2025학년도 2학기 수강신청 안내 |
| `graduation` | 0 | 없음 | 검색 가능한 자료 없음 |

주의할 점:

1. 최신성 로직은 정상이어도 원본 데이터가 오래되면 최신 답변이 아니다. `course_openings`는 현재 데이터 기준 최신 자료가 2025-08-07이다.
2. `general`, `career`, `registration`처럼 넓은 주제에서 최신 1건만 남기면 동시에 유효한 다른 공지가 제외될 수 있다.
3. “같은 주제”를 단순 `topic_key`로 볼지, 학기·공고 종류·문서 시리즈 단위로 볼지 운영 정책 결정이 필요하다.
4. SE 게시판 크롤러는 구현됐지만 현재 저장 데이터와 테스트가 학과 게시판 중심이다.
5. 자동 평가가 아래 5개 실제 품질 간극을 드러냈으며, 기대값을 낮춰 exit 0을 만드는 방식으로 해결하면 안 된다.

측정된 활성 품질 간극:

- false-positive: `registration-period`, `capstone-second-semester`, `scholarship-apply`는 질문 조건과 맞지 않는 최신 주제 문서를 근거 있음으로 판정했다.
- false-negative: `career-recruitment`, `general-recent-department`는 기대한 최신 문서를 검색하지 못해 근거 없음으로 판정했다.
- `course_openings` 원본 최신일이 2025-08-07인 별도 데이터 최신성 문제는 평가 도구가 아니라 P0-2 재수집으로 해결해야 한다.

## 5. 현재 검증 기록

| 검증 | 결과 | 해석 |
| --- | --- | --- |
| backend pytest | 병합 후 main에서 57개 통과 | 평가 schema·evaluator·CLI·dataset·module 실행 계약 포함 |
| backend Ruff | 통과 | 현재 Python 정적 검사 오류 없음 |
| backend line coverage | 이전 측정 68% | Task 6 이후 coverage를 별도 재측정해야 함 |
| frontend Vitest | 병합 후 main에서 3 files, 9 tests 통과 | 컴포넌트 계약 검증 |
| frontend TypeScript | 병합 후 main에서 통과 | 타입 오류 없음 |
| frontend ESLint | 병합 후 main에서 통과 | 현재 lint 오류 없음 |
| Next.js production build | 병합 후 main에서 통과, 정적 페이지 4개 | production 빌드 가능 |
| 재인덱싱 | 게시글 46건, 청크 79개 | local provider 인덱스 생성 가능 |
| 자동 평가 | 30건 중 25건 통과, exit 1 | 도구는 정상 완료됐고 RAG 품질 실패 5건은 후속 수정 대상 |
| 평가 metric | topic 30/30, grounded 25/30, latest-only 28/30, source-title 10/11 | 분류보다 검색·근거 판정 개선 우선 |
| 실제 API | 개설강좌 grounded=true, 범위 밖 식단 grounded=false | 대표 정상·거절 흐름 확인 |
| 브라우저 확인 | 추천 클릭·최근 공지·390px 모바일·console error 0 | 주요 사용자 흐름 수동 확인 |

커버리지에서 확인된 주요 사각지대:

- `backend/app/crawling/seboard.py`: 0%
- `backend/app/openai_service.py`: 33%
- `backend/app/provider_factory.py`: 33%
- `backend/app/main.py`: 61%; `/api/chat`, `/api/health` endpoint 통합 테스트 없음
- `backend/scripts/evaluate.py`는 테스트됐지만 crawl/index CLI와 외부 연동 경로는 추가 보강 필요
- 프론트엔드: 컴포넌트 테스트는 있으나 전체 `page.tsx` fetch 흐름의 자동 통합 테스트와 coverage 기준 없음

## 6. 우선순위 TODO

### P0 — 통합·데이터 정책

| ID | 작업 | 완료 조건 | 필수 검증 |
| --- | --- | --- | --- |
| P0-1 | 브랜치 통합 — **완료** | 기존 기능 `8dc3078`, 자동 평가 PR #2 `6334bdc`로 `main` 통합 | 병합 후 backend 57·frontend 9, Ruff·TypeScript·ESLint·build·CLI 경고 회귀 통과 |
| P0-2 | 공식 데이터 재수집 | 학과·SE 두 소스 수집 성공, 소스별 건수·최신 게시일 기록, `--reset` 재인덱싱 | `--allow-partial` 없이 수집 성공, 샘플 원문 URL·날짜 대조 |
| P0-3 | 최신성 범위 정책 확정 | `topic_key` 1건 정책 유지 또는 `freshness_scope_key` 같은 문서 시리즈 단위 도입 결정 | 동시 유효 공지 2건, 학기 변경, 날짜 누락 fixture 테스트 |
| P0-4 | 주제 규칙 데이터 감사 | 잘못 분류된 최신 공지 수정, `graduation` 자료 부재 처리 결정 | 주제별 표본 5건 수동 라벨링, confusion 기록 |

### P1 — 품질 자동화

| ID | 작업 | 완료 조건 | 필수 검증 |
| --- | --- | --- | --- |
| P1-1 | 자동 평가 CLI — **완료** | 30개 질문의 topic·grounded·latest-only·source-title을 JSON/Markdown으로 출력 | 보고서 생성 후 전체 통과면 exit 0, 측정된 품질 실패면 exit 1; 현재 25건 통과·5건 실패 |
| P1-2 | 백엔드 테스트 보강 | SE crawler fixture, OpenAI mock, provider factory, API endpoint, index/crawl CLI 테스트 | 전체 line coverage 목표 85% 이상, 외부 유료 API 미호출 |
| P1-3 | 프론트 통합/E2E | `page.tsx` fetch 성공·오류·no-answer·추천 재질문과 모바일 흐름 자동화 | coverage 기준 정의, 390px/1280px E2E 통과 |
| P1-4 | 임베딩 fingerprint | provider·모델·차원·청킹·주제 규칙 버전을 인덱스와 함께 저장·검증 | 불일치 인덱스 사용 시 명확한 오류와 재인덱싱 안내 |
| P1-5 | CI 구축 | PR에서 backend/frontend 검사와 production build 자동 실행 | 깨진 테스트·lint·build가 PR을 차단 |

### P2 — 운영 안정성·확장

| ID | 작업 | 완료 조건 | 필수 검증 |
| --- | --- | --- | --- |
| P2-1 | Docker healthcheck | backend readiness 후 frontend 시작, 실패 상태 가시화 | 빈 인덱스·정상 인덱스 compose 시나리오 |
| P2-2 | 관측성 | request ID, topic, 선택 source, 점수, 지연시간 기록; 민감정보 제외 | 로그 샘플과 장애 추적 시나리오 |
| P2-3 | API 보호 | 요청 크기·빈도 제한, CORS 운영값, 오류 응답 표준화 | burst 요청, 잘못된 origin, provider timeout 테스트 |
| P2-4 | 데이터 수명주기 | 증분 수집, 수정·삭제 감지, 인덱스 backup/restore | 삭제 게시글 제거와 복구 훈련 |
| P2-5 | 첨부 문서 처리 | 승인된 PDF/HWP parser와 출처 metadata 보존 | 표·목록·날짜가 있는 fixture 정확성 평가 |
| P2-6 | 의존성 정리 | Vite CJS 경고와 npm advisory 재평가, lockfile 재현성 유지 | clean `npm ci`, audit 검토, 전체 frontend 회귀 |

## 7. 단계별 검증 매트릭스

### 브랜치 통합 전

```powershell
backend/.venv/Scripts/python -m pytest backend/tests -q
backend/.venv/Scripts/python -m ruff check backend
npm --prefix frontend run test -- --run
frontend/node_modules/.bin/tsc.cmd -p frontend/tsconfig.json --noEmit --incremental false
npm --prefix frontend run lint
npm --prefix frontend run build
git diff --check
```

필요 증거: 모든 명령 exit 0, 추적되지 않은 build/index/secret 파일 없음, 변경 파일 목록 검토.

### 데이터 또는 주제 규칙 변경 후

터미널 1:

```powershell
backend/.venv/Scripts/python -m backend.scripts.index --reset
backend/.venv/Scripts/python -m uvicorn backend.app.main:app
```

터미널 2:

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

필요 증거: source별 수집 건수, 주제별 게시글 수, 주제별 최신 제목·게시일, 인덱싱 청크 수, 대표 질문의 source URL과 날짜.

### 파일럿 배포 전

- 최소 30개 평가 질문에서 topic·latest-only·grounded·source 정확도 기록
- 개설강좌·수강신청·장학·취업·캡스톤·졸업·범위 밖 질문 포함
- 공식 원문과 답변의 날짜·대상·신청 경로를 사람이 대조
- SE 게시판 live crawl과 DOM/API fixture를 함께 검증
- OpenAI provider 사용 시 local과 별도로 임계값 재튜닝
- 데스크톱·모바일·키보드 탐색·링크 접근성 확인

### 운영 배포 전

- CI 필수 검사와 Docker healthcheck 통과
- `.env`·API key·Chroma DB·build output이 Git에 포함되지 않았는지 확인
- rate limit, provider timeout, 빈/손상 인덱스, crawler 부분 실패 시나리오 확인
- 로그 민감정보 제거, 인덱스 backup/restore, rollback 절차 검증

## 8. 권장 실행 순서

1. 자동 평가 실패 5건을 재현하는 집중 RAG 결함 수정 계획 수립·구현
2. P0-2 실제 양쪽 데이터 소스를 재수집해 데이터 최신성 확보하고 30개 baseline을 공식 원문과 재검토
3. P0-3/P0-4로 최신성 범위와 주제 규칙을 데이터에 맞게 조정
4. P1-2/P1-3으로 외부 연동·API·페이지 통합 테스트 보강
5. P1-4/P1-5로 잘못된 인덱스 차단과 CI 품질 게이트 구축
6. P2 운영 안정성 항목을 완료한 뒤 파일럿·운영 여부 판단

## 9. 문서 유지 규칙

- 브랜치 통합, provider, 데이터 건수, 최신 게시일, 테스트 수, 검증 결과가 바뀌면 이 문서를 갱신한다.
- 세션별 작업 상세와 커밋 목록은 handoff 문서에 남기고, 이 문서에는 현재 유효한 결론만 유지한다.
- 완료한 TODO는 삭제하지 말고 상태와 검증 근거를 기록한 뒤 완료 이력으로 이동한다.
- 수치가 없는 “완료” 표현을 피하고 명령, exit code, 건수, 날짜, source URL로 근거를 남긴다.

## 10. 현재 중단점과 재개 진입점 (2026-07-13)

RAG 품질·데이터 감사 후속 작업은 `codex/rag-quality-hardening` 브랜치의 전용 worktree에서 진행 중이며 사용자 요청으로 Task 1 이후 중단했다.

- 재개 문서: [`superpowers/handoffs/2026-07-13-rag-quality-data-audit-handoff.md`](superpowers/handoffs/2026-07-13-rag-quality-data-audit-handoff.md)
- 설계 커밋: `5bfd23b`
- 구현 계획 커밋: `93dd6d7`
- 현재 기능 HEAD: `4093c94 feat: validate retrieval evidence policy`
- Task 1: TDD 구현·60개 backend 회귀·명세 리뷰 통과
- 미완료 게이트: Task 1 코드 품질 리뷰가 중단되어 재실행 필요
- 다음 구현: Task 2 질문 의도 분석부터 Task 9 전체 검증까지 순차 진행
- 현재 품질 기준선: local 평가 25/30, 실패 5건, quality exit 1
- 원격 상태: 기능 브랜치 push/PR 미수행

다음 작업자는 인수인계 문서의 `1. 재개 진입점` 명령으로 시작하고, Task 1 품질 리뷰를 통과시키기 전에는 Task 2를 완료 처리하지 않는다.
