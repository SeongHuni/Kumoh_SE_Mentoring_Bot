# SE Mentor Bot 프로젝트 상태와 다음 작업

> 기준일: 2026-07-12
> 기준 브랜치: `codex/topic-latest`
> 구현 기준 커밋: `8a02351 docs: finalize topic latest handoff`

이 문서는 프로젝트의 현재 진행도, 남은 위험, 개선 TODO, 단계별 검증 기준을 한곳에서 관리하는 운영 기준 문서다. 세션별 상세 이력은 [`superpowers/handoffs/2026-07-12-topic-latest-handoff.md`](superpowers/handoffs/2026-07-12-topic-latest-handoff.md), RAG 설계는 [`RAG_ARCHITECTURE.md`](RAG_ARCHITECTURE.md)를 참고한다.

## 1. 현재 결론

- 계획된 **주제별 최신 RAG와 추천 UX 기능은 구현·검증 완료** 상태다.
- 구현은 `codex/topic-latest` 브랜치에 있고 **`main`에는 아직 병합되지 않았다**.
- 로컬 프로토타입은 실행 가능하지만, **실데이터 최신성·SE 게시판 수집·자동 평가·운영 안전성은 추가 검증이 필요**하다.
- 따라서 현재 단계는 `기능 완료 → 통합 대기`이며, 파일럿 또는 운영 완료로 판단하지 않는다.

## 2. 단계별 진행도

| 영역 | 상태 | 완료 근거 | 다음 조건 |
| --- | --- | --- | --- |
| 요구사항·설계 | 완료 | 최신성·추천 UX 설계와 Task 1~8 계획 존재 | 정책 변경 시 설계와 이 문서 동시 갱신 |
| 백엔드 RAG | 완료 | 주제 분류, 최신성 계산, Chroma filter, 추천 질문·최근 공지 구현 | 실데이터 평가와 미검증 provider 보강 |
| 프론트엔드 | 완료 | A 집중형 채팅, 출처·추천 chip·최근 공지, 모바일 대응 | 페이지 통합/E2E 및 접근성 자동화 |
| 단위·컴포넌트 테스트 | 통과 | backend 26개, frontend 9개 | 커버리지 사각지대 해소 |
| 문서·운영 절차 | 완료 | README와 RAG 운영 문서, 재인덱싱 절차 존재 | 데이터/환경 변경 때 현행화 |
| 데이터 준비 | 부분 완료 | 학과 게시글 46건, 79청크 인덱싱 확인 | 양쪽 공식 소스 재수집과 최신성 감사 |
| 브랜치 통합 | 미완료 | `main`과 `codex/topic-latest` 분리 | 병합 또는 PR 후 전체 회귀 검증 |
| 파일럿 준비 | 차단 | 자동 평가·실수집·주제 세분화 검증 부족 | P0·P1 TODO 완료 |
| 운영 준비 | 미착수 | CI, 관측성, rate limit, backup 기준 미완성 | 운영 검증 매트릭스 충족 |

현재 실행·브랜치 스냅샷:

| 항목 | 값 |
| --- | --- |
| `main` HEAD | `f78be6a docs: include frontend build cache ignore` |
| 기능 구현 기준 HEAD | `8a02351 docs: finalize topic latest handoff` |
| 문서 작성 전 브랜치 분기 | `main` 전용 5커밋 / 기능 브랜치 전용 17커밋 |
| provider | `local` |
| embedding | `local-hash-embedding-v1`, 1,536차원 |
| answer | `local-extractive-answer-v1` |
| retrieval | `top_k=5`, `min_score=0.09` |
| 데이터·인덱스 | 게시글 46건, 청크 79개 |

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

## 5. 현재 검증 기록

| 검증 | 결과 | 해석 |
| --- | --- | --- |
| backend pytest | 26개 통과 | 구현된 핵심 규칙의 회귀 기준 존재 |
| backend Ruff | 통과 | 현재 Python 정적 검사 오류 없음 |
| backend line coverage | 68% | 핵심 RAG는 높지만 외부 연동 경로가 낮음 |
| frontend Vitest | 3 files, 9 tests 통과 | 컴포넌트 계약 검증 |
| frontend TypeScript | 통과 | 타입 오류 없음 |
| frontend ESLint | 통과 | 현재 lint 오류 없음 |
| Next.js production build | 통과, 정적 페이지 4개 | production 빌드 가능 |
| 재인덱싱 | 게시글 46건, 청크 79개 | local provider 인덱스 생성 가능 |
| 실제 API | 개설강좌 grounded=true, 범위 밖 식단 grounded=false | 대표 정상·거절 흐름 확인 |
| 브라우저 확인 | 추천 클릭·최근 공지·390px 모바일·console error 0 | 주요 사용자 흐름 수동 확인 |

커버리지에서 확인된 주요 사각지대:

- `backend/app/crawling/seboard.py`: 0%
- `backend/app/openai_service.py`: 33%
- `backend/app/provider_factory.py`: 33%
- `backend/app/main.py`: 61%; `/api/chat`, `/api/health` endpoint 통합 테스트 없음
- `backend/scripts`: 테스트 중 import되지 않음
- 프론트엔드: 컴포넌트 테스트는 있으나 전체 `page.tsx` fetch 흐름의 자동 통합 테스트와 coverage 기준 없음

## 6. 우선순위 TODO

### P0 — 통합·데이터 정책

| ID | 작업 | 완료 조건 | 필수 검증 |
| --- | --- | --- | --- |
| P0-1 | `codex/topic-latest` 통합 | `main` 병합 또는 PR 승인, 양쪽에 중복 적용된 문서 커밋을 검토하고 의도한 기능·문서 변경만 반영 | 병합 전 충돌 rehearsal, 병합 후 backend/frontend 전체 회귀, `git diff --check` |
| P0-2 | 공식 데이터 재수집 | 학과·SE 두 소스 수집 성공, 소스별 건수·최신 게시일 기록, `--reset` 재인덱싱 | `--allow-partial` 없이 수집 성공, 샘플 원문 URL·날짜 대조 |
| P0-3 | 최신성 범위 정책 확정 | `topic_key` 1건 정책 유지 또는 `freshness_scope_key` 같은 문서 시리즈 단위 도입 결정 | 동시 유효 공지 2건, 학기 변경, 날짜 누락 fixture 테스트 |
| P0-4 | 주제 규칙 데이터 감사 | 잘못 분류된 최신 공지 수정, `graduation` 자료 부재 처리 결정 | 주제별 표본 5건 수동 라벨링, confusion 기록 |

### P1 — 품질 자동화

| ID | 작업 | 완료 조건 | 필수 검증 |
| --- | --- | --- | --- |
| P1-1 | 자동 평가 CLI | 질문별 topic·grounded·latest-only·source 적중을 JSON/Markdown으로 출력 | 최소 30개 대표 질문, 실패 시 non-zero exit |
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

1. P0-1 브랜치 통합 방식을 확정하고 통합 브랜치에서 전체 회귀 실행
2. P0-2 실제 양쪽 데이터 소스를 재수집해 데이터 최신성 확보
3. P0-3/P0-4로 최신성 범위와 주제 규칙을 데이터에 맞게 조정
4. P1-1 자동 평가 CLI와 30개 이상 평가셋 구축
5. P1-2/P1-3으로 외부 연동·API·페이지 통합 테스트 보강
6. P1-4/P1-5로 잘못된 인덱스 차단과 CI 품질 게이트 구축
7. P2 운영 안정성 항목을 완료한 뒤 파일럿·운영 여부 판단

## 9. 문서 유지 규칙

- 브랜치 통합, provider, 데이터 건수, 최신 게시일, 테스트 수, 검증 결과가 바뀌면 이 문서를 갱신한다.
- 세션별 작업 상세와 커밋 목록은 handoff 문서에 남기고, 이 문서에는 현재 유효한 결론만 유지한다.
- 완료한 TODO는 삭제하지 말고 상태와 검증 근거를 기록한 뒤 완료 이력으로 이동한다.
- 수치가 없는 “완료” 표현을 피하고 명령, exit code, 건수, 날짜, source URL로 근거를 남긴다.
