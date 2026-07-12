# SE Mentor Bot 주제별 최신성·추천 UX 인수인계

> 기록 시점: 2026-07-12, Task 1~8 구현·전체 검증 완료

## 작업 위치

- 저장소: `C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot`
- 격리 worktree: `C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot\.worktrees\topic-latest`
- 구현 브랜치: `codex/topic-latest`
- 기준 브랜치: `main`
- 최근 구현 커밋: `fb1d84d fix: calibrate local retrieval threshold`
- 기록 직전 브랜치 HEAD: `fb1d84d fix: calibrate local retrieval threshold`
- 설계: `docs/superpowers/specs/2026-07-11-rag-topic-latest-design.md`
- 구현 계획: `docs/superpowers/plans/2026-07-11-rag-topic-latest-implementation.md`

메인 checkout과 worktree를 혼동하지 않는다. 구현·테스트·커밋은 위 worktree에서 진행한다.

## 목표와 확정된 동작

1. `data/topic_rules.json`에서 주제, 키워드, 추천 질문을 관리한다.
2. 같은 주제의 게시글은 `published_at`이 가장 최신인 게시글만 RAG 근거로 사용한다.
3. 게시일이 없거나 잘못된 형식이면 `crawled_at`을 최신성 비교에 사용한다.
4. 구체적인 주제 질문은 `is_latest_topic=true`와 `topic_key`를 함께 Chroma filter로 적용한다.
5. 일반 질문은 모든 주제에서 최신으로 표시된 게시글만 검색한다.
6. 근거가 없어도 provider를 호출하지 않은 채 추천 질문과 최근 공지를 반환한다.
7. 프론트엔드는 A 집중형 채팅을 유지하고 답변 → 출처 → 추천 질문 → 최근 공지 순으로 표시한다.

## 완료된 작업

### Task 1 — 주제 규칙과 도메인 모델

- 커밋: `a112502 feat: add configurable topic rules`
- `TopicCatalog`, 규칙 로더, 주제 JSON, 환경설정 경로 추가
- `BoardPost`와 `TextChunk`에 주제 metadata 추가
- 기존 chunk/vector 생성 지점의 필수 필드 호환 처리
- 사양 리뷰와 품질 리뷰 통과

### Task 2 — 최신성 판별과 enrichment

- 커밋: `bc1270d feat: mark latest posts by topic`
- `freshness.py`, `topic_classifier.py` 추가
- 게시일 우선 및 수집일 fallback 구현
- 주제별 최신 게시글만 `is_latest_topic=true`로 표시
- 사양 리뷰와 품질 리뷰 통과

### Task 3 — Chroma metadata와 서비스 wiring

- 커밋: `d1a01fc feat: filter vector search by latest topic`
- Chroma topic metadata 저장·복원 및 optional `where` 전달
- 인덱싱 시 topic enrichment 연결
- `main.get_rag_service()`가 catalog와 46개 posts를 주입하는 회귀 테스트 추가
- 사양 리뷰와 품질 리뷰 통과

### Task 4 — RAG 응답·추천 질문·최근 공지

- 커밋: `4b91844 feat: return topic-aware chat follow-ups`
- topic-aware 최신 검색 filter 적용
- `RecentNotice`, `suggested_questions`, `recent_notices` 응답 필드 추가
- 주제 추천이 부족하면 general 추천으로 채우는 fallback 구현
- 최근 공지 최신성 정렬과 URL 중복 제거
- 근거 부족 시 provider 미호출과 follow-up 반환
- backend 테스트 25개 통과, Task 4 대상 Ruff 통과
- 사양 리뷰와 품질 리뷰 통과

### Task 5 — 프론트엔드 후속 콘텐츠 컴포넌트

- 커밋: `18ae704 test: add frontend follow-up components`
- `Message`, `Source`, `RecentNotice` TypeScript 타입 분리
- `ChatMessage`, `RecommendationChips`, `RecentNoticeList` 컴포넌트 추가
- Vitest·Testing Library 환경과 컴포넌트 테스트 7개 추가
- 빈 배열, disabled 추천 버튼, user message의 assistant-only 영역 미표시까지 회귀 테스트
- Task 6 CSS 계약과 맞는 `notice-heading`, `notice-card`, `notice-arrow` markup 적용
- `*.tsbuildinfo` ignore 추가
- clean `npm ci`, 테스트, TypeScript, ESLint, production build 통과
- 사양 리뷰와 품질 리뷰 통과

검증 기록:

- `npm ci --ignore-scripts --dry-run`: exit 0
- clean `npm ci --ignore-scripts`: exit 0
- Vitest: 3 files, 7 tests passed
- TypeScript `--noEmit --incremental false`: exit 0
- ESLint: exit 0
- Next.js production build: exit 0, static pages 4개 생성
- 런타임 버전 유지: Next 15.5.20, React/React DOM 19.1.1

### Task 6 — 페이지 통합과 읽기 쉬운 스타일

- 커밋: `07fd1b2 feat: show chat recommendations and recent notices`
- API의 `suggested_questions`와 `recent_notices`를 assistant message state에 저장
- 오류 message에는 두 배열을 빈 배열로 유지
- 기존 말풍선·출처 markup을 `ChatMessage`로 교체
- 추천 질문 클릭은 기존 `submitQuestion` 경로와 로딩 잠금을 재사용
- 답변 줄바꿈·긴 문자열, 추천 chip, 최근 공지 카드, 모바일 가로 스크롤 스타일 추가
- 초기 추천 질문 중복 렌더링을 실패 테스트로 재현한 뒤 기존 composer 추천 영역과 죽은 CSS 제거
- Vitest 3 files, 9 tests 통과
- TypeScript, ESLint, Next.js production build 통과
- 서브에이전트 사용 한도 종료 후 현재 세션에서 TDD·검증 절차를 유지해 완료

### Task 7 — 운영 문서와 평가 질문

- 커밋: `fc150e8 docs: document topic freshness operations`
- README와 RAG 문서에 `data/topic_rules.json` 단일 유지보수 지점 기록
- 유효한 `published_at` 우선, 누락·파싱 실패 시 `crawled_at` fallback 기록
- 같은 주제의 과거 게시글 제외, Chroma `where` filter, API 후속 정보 필드 기록
- 원본·규칙 변경 후 `backend/.venv/Scripts/python -m backend.scripts.index --reset` 절차 기록
- 평가 데이터에 `course_openings` 최신성 질문과 범위 밖 `general` 질문 추가
- JSON 파싱과 `git diff --check` 통과

### Task 8 — 전체 검증과 실제 UI 확인

- Ruff import 정렬 1건을 `95abd9b test: satisfy backend import lint`로 수정
- 실제 개설강좌 질문이 `grounded=false`인 현상을 재현하고 주제·filter·검색 점수를 단계별 진단
- 원인: 로컬 해시 임베딩 운영 보정값은 `0.09`인데 코드·예시 기본값은 `0.20`이었던 불일치
- 실패 회귀 테스트를 먼저 추가한 뒤 `fb1d84d fix: calibrate local retrieval threshold`로 기본값·문서 통일
- 개설강좌 재정렬 점수 `0.1543`은 통과하고 범위 밖 식단 최고 점수 `0.0194`는 계속 거절되는 것을 확인
- 백엔드 pytest 26개, 전체 Ruff, 프론트 Vitest 9개, TypeScript, ESLint 모두 통과
- Next.js production build 통과: 정적 페이지 4개
- 로컬 재인덱싱 통과: 게시글 46건, 청크 79개, `local-hash-embedding-v1`
- 실제 API: 개설강좌 `grounded=true`, source 1건·게시일 `2025-08-07`; 범위 밖 식단 `grounded=false`, source 0건
- 실제 UI: 답변·출처·추천 질문 3개·최근 공지 3개 렌더링, 추천 질문 클릭 재전송 확인
- 390px viewport에서 문서·메시지 가로 넘침 없음, 추천 chip만 내부 가로 스크롤, 공지 카드 viewport 안에 유지
- 브라우저 console error 0건
- 최종 변경 범위 자체 리뷰에서 차단 이슈 없음

## 현재 상태

- worktree는 clean이다.
- Task 1~8 구현·문서화·전체 검증이 완료됐다.
- 구현 브랜치 `codex/topic-latest`는 통합 방식 결정만 남았다.
- Task 5의 Vitest CJS API deprecation warning은 비차단 경고다.
- npm은 기존 dependency advisory 5건과 deprecated transitive package 1건을 보고했지만 Task 5 기능 검증을 막지 않는다.

## 즉시 재개 절차

```powershell
Set-Location C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot\.worktrees\topic-latest
git status --short --branch
git show --stat fb1d84d
Get-Content docs/superpowers/plans/2026-07-11-rag-topic-latest-implementation.md
```

기능을 다시 확인하려면 다음 명령을 실행한다.

```powershell
backend/.venv/Scripts/python -m pytest backend/tests -q
backend/.venv/Scripts/python -m ruff check backend
npm --prefix frontend run test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
backend/.venv/Scripts/python -m backend.scripts.index --reset
```

## 남은 작업

필수 구현 작업은 없다. 다음 작업자는 사용자와 통합 방식을 정한다.

1. `codex/topic-latest`를 로컬 `main`에 병합
2. 브랜치를 원격에 push하고 PR 생성
3. 브랜치를 그대로 유지하고 추가 평가를 진행

메인 checkout에는 별도 사용자 변경이 있을 수 있으므로 병합 전 `git status`와 양쪽 브랜치의 공통 조상을 확인한다.

## 알려진 주의사항

- 기존 Chroma 인덱스는 topic metadata가 없으므로 반드시 다음 명령으로 재생성한다.

```powershell
backend/.venv/Scripts/python -m backend.scripts.index --reset
```

- `backend/tests/test_topic_rules.py` import order 오류는 `95abd9b`에서 해결됐고 전체 Ruff가 통과했다.
- `frontend/package-lock.json`은 clean `npm ci`로 검증됐고 런타임 dependency 버전은 유지됐다.
- Vitest가 Vite CJS Node API deprecation warning을 출력한다. 현재 비차단이며 ESM config 전환은 별도 정리 대상이다.
- `.env`, API key, Chroma DB, build output, `tsconfig.tsbuildinfo`를 커밋하지 않는다.
- 메인 checkout의 별도 사용자 변경을 worktree에서 되돌리거나 덮어쓰지 않는다.

## 완료 판단 기준

- [x] 개설강좌 질문에서 같은 주제의 최신 source만 반환
- [x] 답변 뒤 출처·추천 질문·최근 공지가 표시
- [x] 추천 질문 클릭으로 새 질문 전송
- [x] 근거 부족 질문은 추측하지 않고 follow-up만 제공
- [x] 데스크톱과 모바일에서 읽기 쉬운 A 집중형 채팅 유지
- [x] backend/frontend 테스트, Ruff, ESLint, production build 모두 통과
