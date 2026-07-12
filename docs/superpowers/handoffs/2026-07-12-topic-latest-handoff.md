# SE Mentor Bot 주제별 최신성·추천 UX 인수인계

> 기록 시점: 2026-07-12, Task 5 리뷰 완료·Task 6 시작 직전

## 작업 위치

- 저장소: `C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot`
- 격리 worktree: `C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot\.worktrees\topic-latest`
- 구현 브랜치: `codex/topic-latest`
- 기준 브랜치: `main`
- 최근 구현 커밋: `18ae704 test: add frontend follow-up components`
- 현재 브랜치 HEAD: `ab06f63 docs: include frontend build cache ignore`
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

## 현재 상태

- worktree는 clean이다.
- Task 1~5 구현 및 각 task의 사양·품질 리뷰가 완료됐다.
- 다음 작업은 Task 6 `page.tsx` 통합과 `globals.css` 스타일이다.
- Task 5의 Vitest CJS API deprecation warning은 비차단 경고다.
- npm은 기존 dependency advisory 5건과 deprecated transitive package 1건을 보고했지만 Task 5 기능 검증을 막지 않는다.

## 즉시 재개 절차

```powershell
Set-Location C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot\.worktrees\topic-latest
git status --short --branch
git show --stat 18ae704
Get-Content docs/superpowers/plans/2026-07-11-rag-topic-latest-implementation.md
```

Task 6은 `page.tsx`와 `globals.css`만 수정하며, 기존 Task 5 컴포넌트의 public props와 class contract를 재사용한다.

```powershell
npm --prefix frontend run test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build
```

## 남은 작업

### Task 6 — 페이지 통합과 스타일

- `page.tsx`가 API의 `suggested_questions`, `recent_notices`를 message state에 저장
- `ChatMessage`로 기존 말풍선·출처 UI 교체
- 추천 질문 클릭 시 기존 `submitQuestion` 경로 재사용
- 오류 message에는 두 배열을 빈 배열로 설정
- `globals.css`에 답변 본문, 추천 chip, 최근 공지 카드, 모바일 스타일 추가
- 프론트 테스트·lint·build 후 리뷰

### Task 7 — 운영 문서와 평가 질문

- README와 RAG 문서에 `topic_rules.json`, 최신성 규칙, `--reset` 재인덱싱 절차 기록
- `data/evaluation/questions.json`에 개설강좌 최신성 질문과 범위 밖 질문 추가
- 문서 `git diff --check` 후 커밋·리뷰

### Task 8 — 전체 검증과 UI 확인

- backend pytest 전체
- backend Ruff 전체
- frontend Vitest 전체
- frontend ESLint
- frontend production build
- 데이터 재인덱싱
- 브라우저에서 개설강좌 최신 source, 추천 질문 클릭, 최근 공지, no-answer, 모바일 viewport 확인
- 최종 전체 코드 리뷰

## 알려진 주의사항

- 기존 Chroma 인덱스는 topic metadata가 없으므로 반드시 다음 명령으로 재생성한다.

```powershell
backend/.venv/Scripts/python -m backend.scripts.index --reset
```

- 전체 Ruff에는 `backend/tests/test_topic_rules.py` import order 오류가 남아 있다. 최종 검증 전에 Ruff 자동 수정 또는 수동 import 정렬로 해결하고 전체 Ruff를 다시 실행한다.
- `frontend/package-lock.json`은 clean `npm ci`로 검증됐고 런타임 dependency 버전은 유지됐다.
- Vitest가 Vite CJS Node API deprecation warning을 출력한다. 현재 비차단이며 ESM config 전환은 별도 정리 대상이다.
- `.env`, API key, Chroma DB, build output, `tsconfig.tsbuildinfo`를 커밋하지 않는다.
- 메인 checkout의 별도 사용자 변경을 worktree에서 되돌리거나 덮어쓰지 않는다.

## 완료 판단 기준

- 개설강좌 질문에서 같은 주제의 최신 source만 반환
- 답변 뒤 출처·추천 질문·최근 공지가 표시
- 추천 질문 클릭으로 새 질문 전송
- 근거 부족 질문은 추측하지 않고 follow-up만 제공
- 데스크톱과 모바일에서 읽기 쉬운 A 집중형 채팅 유지
- backend/frontend 테스트, Ruff, ESLint, production build 모두 통과
