# 유지보수성·운영 안전성 개선 설계

- 작성일: 2026-07-15
- 상태: 사용자 설계 승인 완료, 구현 전 명세
- 기준 커밋: `b99f997`
- 작업 브랜치: `codex/maintainability-audit`

## 1. 목적

현재 구현을 대규모로 다시 짜지 않고, 검토로 확인된 문서 불일치와 런타임 위험을
테스트 가능한 작은 변경으로 해결한다. 최종적으로 새 작업자가 다음 작업을 수행할 때
서로 충돌하는 설명 없이 같은 명령과 판단 기준을 사용할 수 있어야 한다.

- 개발 환경 구성과 전체 품질 검증
- 데이터 수집, 인덱싱, 평가, 데이터 감사 실행
- 프론트엔드 API 연결과 오류 원인 파악
- Docker Compose 구성 점검
- 현재 상태와 남은 위험 확인

## 2. 기준 상태와 감사 결과

격리 worktree에서 구현 전 기준을 검증했다.

| 항목 | 기준 결과 |
|---|---|
| Backend pytest | 154개 통과 |
| Backend coverage | 91.42%, 85% gate 통과 |
| Ruff | 통과 |
| Frontend Vitest | 3 files, 9 tests 통과 |
| TypeScript / ESLint | 통과 |
| Next.js production build | 통과 |
| 운영 npm 의존성 감사 | 취약점 0건 |
| 전체 npm 의존성 감사 | 개발 도구 5건: moderate 3, high 1, critical 1 |
| Docker 실행 검증 | 현재 호스트에 Docker 미설치로 실행 불가 |

유지보수성 기준 평가는 6/10이다. 코드 분리와 자동 테스트는 양호하지만, 현재 상태를
설명하는 문서가 실제 구현과 어긋나고 일부 관리 명령이 설정 또는 인덱스 호환성을
무시한다.

## 3. 확인된 문제

### 3.1 문서와 실제 상태 불일치

- 실제 추적 데이터는 금오공대 게시글 50건, SE 게시글 0건이고 현재 인덱스는
  84청크인데 일부 문서에는 46건/79청크 또는 양쪽 게시판 약 100건으로 적혀 있다.
- `README.md`의 SE 수집 예시는 같은 문서의 robots/권한 제한 설명과 충돌한다.
- 이미 구현된 strict manifest와 임베딩 fingerprint 검증을 미구현으로 설명하는
  RAG 문서가 있다.
- `AGENTS.md`에는 scaffold 이전 구조, 존재하지 않는 빌드 상태, 불완전한 테스트 설치
  명령이 남아 있다.
- 날짜가 있는 과거 계획 문서와 현재 운영 문서의 우선순위가 명시되지 않았다.

### 3.2 백엔드 관리 명령의 fail-open 동작

- `crawl.py`의 `--seboard-limit` 기본값이 50이라 기본 명령만 실행해도 비허용 소스에
  접근할 수 있다.
- `evaluate.py`의 기본 local provider는 다른 embedding provider로 만든 인덱스를
  조회할 수 있으며, 현재는 manifest 호환성을 먼저 검사하지 않는다.
- `audit_data.py`의 기본 경로는 `Settings`가 아니라 저장소 기본값으로 고정되어 있어
  운영자가 인덱싱한 데이터와 다른 파일을 감사할 수 있다.

### 3.3 프론트엔드 요청 경계 부족

- 화면 컴포넌트가 HTTP 요청, JSON 파싱, 오류 변환, 메시지 조립을 모두 담당한다.
- 응답 제한 시간이 없고, HTML 또는 빈 오류 응답이면 실제 서버 오류 대신 JSON 파싱
  오류가 사용자에게 노출될 수 있다.
- 첫 안내 문구가 현재 존재하지 않는 SE 게시판 데이터도 사용한다고 설명한다.
- 성공·서버 오류·네트워크 timeout을 아우르는 페이지 수준 회귀 테스트가 없다.

### 3.4 컨테이너 운영 경계 부족

- Compose가 `NEXT_PUBLIC_API_URL`을 하드코딩해 `.env.example`의 값을 무시한다.
- backend/frontend healthcheck와 시작 조건이 없다.
- 기존 `/api/health`는 RAG readiness 상태를 자세히 제공하지만 컨테이너 프로세스
  자체의 liveness와 구분되지 않는다.

### 3.5 개발 테스트 도구 취약점

- production 의존성에는 알려진 취약점이 없다.
- 현재 Vitest 2 계열과 전이 Vite/esbuild 도구 체인에는 `npm audit` 기준 critical 1건을
  포함한 5건이 있다.
- 자동 강제 수정은 메이저 버전 변경이므로 설정과 테스트 호환성을 검증하며 명시적으로
  업그레이드해야 한다.

## 4. 문서 정보 구조

현재 문서의 역할을 다음과 같이 고정한다.

| 문서 | 책임 |
|---|---|
| `README.md` | 가장 짧은 설치, 실행, 검증 진입점 |
| `docs/PROJECT_STATUS.md` | 데이터 수, 테스트 수, 준비도, 위험, TODO 등 변동 상태 |
| `docs/RAG_ARCHITECTURE.md` | RAG 문서 목차와 변경되지 않는 핵심 불변식 |
| `docs/rag/operations-evaluation.md` | 운영 명령의 단일 기준 |
| 그 외 `docs/rag/*.md` | 세부 동작과 정책, 중복된 변동 수치 최소화 |
| `.env.example` | 지원 설정과 기본값의 단일 기준 |
| `AGENTS.md` | 에이전트·기여자 규칙, 상세 운영 명령은 위 문서로 위임 |

`docs/superpowers/specs`, `plans`, `handoffs`와 `docs/reference`는 작성 당시의 판단을
보존하는 역사 자료다. 사실 오류를 고치기 위해 과거 기록을 대량 수정하지 않고,
현재 문서에서 우선순위를 안내한다.

## 5. 구현 설계

### 5.1 문서 정합성

1. README의 현재 데이터 범위와 실행 예시를 50건/SE 비활성 상태에 맞춘다.
2. 변동 수치는 가급적 `PROJECT_STATUS.md`만 소유하게 하고 세부 RAG 문서는 현재
   구현 원칙을 설명한다.
3. strict manifest, fingerprint, 최신 주제 우선, 추천 질문, 최근 공지의 완료 상태를
   실제 코드와 맞춘다.
4. embedding 변경만 재인덱싱이 필요하며 chat model 변경은 재인덱싱과 무관하다는
   경계를 명시한다.
5. `AGENTS.md`의 구조, 설치, 테스트, Git 안내를 현재 저장소에 맞춘다.
6. Docker에서 `NEXT_PUBLIC_API_URL`이 build-time 값이라는 점과 현재 Docker 실기동
   미검증 상태를 명시한다.

### 5.2 크롤링 안전장치

`backend/app/crawling/seboard.py`와 SE 데이터는 변경하지 않는다. 공용 실행 진입점만
fail-closed로 만든다.

- `--seboard-limit` 기본값을 0으로 변경한다.
- 양수 limit에는 `--seboard-permission-confirmed` 같은 명시적 확인 옵션을 요구한다.
- 확인이 없으면 crawler 생성이나 네트워크·브라우저 접근 전에 종료 코드 2와 명확한
  안내를 반환한다.
- 기본 실행이 Kumoh 수집만 수행하는지, 비승인 양수 limit이 crawler를 호출하지
  않는지 테스트한다.

이 확인 옵션은 법적 승인을 대신하지 않는다. 승인 근거와 허용 API가 확보되기 전
운영 문서는 계속 `--seboard-limit 0`만 안내한다.

### 5.3 평가 인덱스 호환성

- 선택한 평가 provider를 반영한 `effective_settings`로 vector store를 연다.
- 기존 `assess_index_compatibility(settings=..., store=...)`를 재사용한다.
- `compatible`이 아니면 provider 생성과 첫 질문 전에 원인별 안내와 종료 코드 2를
  반환한다.
- local, configured, auto 조합에서 일치 인덱스는 진행되고 settings/content/count/
  manifest 불일치는 질문 실행 전에 중단되는지 테스트한다.
- README와 운영 문서에서 인덱싱·평가 provider가 반드시 같아야 함을 명시한다.

### 5.4 데이터 감사 설정 일치

- `audit_data.py`의 기본 posts/topic-rules 경로를 `get_settings()`에서 가져온다.
- 명시적 CLI 인자는 설정값보다 우선한다.
- 환경 변수로 사용자 정의 경로를 지정한 테스트에서 실제 선택 파일이 보고서를
  결정하는지 확인한다.

### 5.5 프론트엔드 HTTP 경계

- API payload 타입과 요청 함수를 별도 모듈로 분리한다.
- 요청 함수는 `AbortController` 기반 기본 timeout을 제공하고 테스트에서는 timeout과
  fetch를 주입할 수 있게 한다.
- JSON, FastAPI `detail`, 일반 텍스트, 빈 응답, 네트워크 오류를 일관된 한국어 사용자
  메시지로 변환한다.
- `page.tsx`는 폼·메시지 상태와 렌더링만 담당한다.
- 초기 안내는 현재 금오공대 공식 공지 데이터를 사용하며 SE 데이터는 승인 전
  제공되지 않는다고 정확히 표현한다.
- 페이지 통합 테스트에 성공 응답, 오류 응답, timeout, 추천 질문 재전송을 포함한다.

추천 질문, 최근 공지, 출처, grounded 표시는 현재 API 계약을 유지한다.

### 5.6 liveness와 readiness

- `/api/live`를 추가해 FastAPI 프로세스가 요청을 처리할 수 있는지만 200으로 응답한다.
- 기존 `/api/health`는 provider, index, manifest를 포함한 RAG readiness 진단으로
  유지한다.
- backend container healthcheck는 `/api/live`를 사용한다.
- frontend는 backend 프로세스가 healthy인 뒤 시작하지만, `needs_index` 상태에서도
  UI가 시작되어 운영 안내를 표시할 수 있어야 한다.
- frontend healthcheck는 Node 런타임으로 `/` 응답을 검사해 별도 curl 패키지를
  추가하지 않는다.
- Compose build arg는 `${NEXT_PUBLIC_API_URL:-http://localhost:8000}`을 사용한다.

### 5.7 개발 테스트 도구 업데이트

- Vitest, Vite React plugin과 필요한 jsdom 도구를 서로 호환되는 비취약 메이저
  버전으로 명시적으로 업데이트한다.
- 지원 Node 범위를 실제 도구의 engine 요구 사항과 맞춘다.
- lockfile을 재생성한 뒤 production audit 0건과 전체 audit 0건을 목표로 한다.
- 전체 audit에 업스트림 미해결 항목이 남으면 production 영향 여부, 완화책, 후속
  버전을 `PROJECT_STATUS.md`에 기록하며 숨기지 않는다.

## 6. 오류 처리 원칙

- 관리 명령은 불확실한 상태에서 실행을 계속하지 않고 종료 코드 2를 사용한다.
- 사용자 화면에는 내부 stack trace나 JSON parse 오류를 노출하지 않는다.
- timeout, 연결 실패, 서버 검증 오류는 서로 구분 가능한 문구를 제공한다.
- RAG가 준비되지 않은 상태는 프로세스 장애와 분리해 `/api/health`에서 진단한다.
- 데이터·인덱스·설정 불일치는 자동 보정하지 않고 재인덱싱 명령을 안내한다.

## 7. 비범위

- `backend/app/crawling/seboard.py` 내부 구현 변경
- SE 게시판 데이터 수집·생성·활성화
- 과거 계획·handoff 문서의 사실관계 일괄 재작성
- RAG 검색 알고리즘 또는 prompt의 대규모 변경
- 인증, 운영 배포, 외부 모니터링 시스템 도입
- 원본 데이터의 timestamp snapshot 저장 정책 구현

## 8. 테스트 전략

제품 변경은 실패하는 테스트를 먼저 추가한 뒤 최소 구현으로 통과시킨다.

1. Backend 단위·CLI 테스트
   - SE 기본 비활성 및 승인 없는 명시 실행 차단
   - 평가 manifest/provider 불일치 fail-closed
   - 데이터 감사 환경 경로 우선순위
   - `/api/live`와 기존 `/api/health` 계약
2. Frontend 단위·통합 테스트
   - HTTP 성공, FastAPI 오류, non-JSON 오류, timeout
   - 메시지 렌더링, 추천 질문 재전송, 최근 공지 유지
3. 전체 gate
   - backend pytest + coverage 85% 이상, Ruff
   - frontend test, typecheck, lint, production build
   - `npm audit --omit=dev`, `npm audit`
   - `git diff --check`
   - 추적 Markdown 상대 링크 검사
4. Docker
   - 가능한 환경에서 `docker compose config`, build, healthcheck를 실행한다.
   - 현재 호스트에는 Docker가 없으므로 실행하지 못한 검증은 완료로 표시하지 않는다.

## 9. 완료 기준

- 현재 문서에서 데이터 출처, 수치, manifest 구현 상태, 운영 명령이 충돌하지 않는다.
- 기본 crawl 명령은 SE crawler를 생성하지 않는다.
- 평가가 호환되지 않는 인덱스에 질문하지 않는다.
- 데이터 감사 기본 경로가 애플리케이션 설정과 같다.
- 프론트엔드는 timeout과 비정형 오류를 읽을 수 있는 메시지로 표시한다.
- Compose의 API URL과 healthcheck가 설정 가능하고 의미가 문서화된다.
- production npm audit에는 취약점이 없고 개발 도구 감사 결과도 명시된다.
- 기준 품질 gate가 모두 회귀 없이 통과한다.
- `PROJECT_STATUS.md`에 완료 항목과 Docker 실기동 등 남은 검증이 분리되어 있다.

## 10. 핵심 결정

1. 문서의 현재 상태와 역사 기록을 분리해 단일 기준을 만든다.
2. SE 구현은 건드리지 않되 공용 진입점의 우발적 수집은 fail-closed로 차단한다.
3. 구조 개편보다 검증 가능한 경계와 회귀 테스트를 우선한다.
