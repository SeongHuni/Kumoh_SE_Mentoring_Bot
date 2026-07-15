# SE Mentor Bot 프로젝트 상태와 다음 작업

> 기준일: 2026-07-15
> 기준 브랜치: `main`
> 통합 범위: 원격 최신 데이터·RAG 수정(`0d766a9`) + RAG 품질·데이터 감사 Task 1~9
> 상세 이력: [`superpowers/handoffs/2026-07-13-rag-quality-data-audit-handoff.md`](superpowers/handoffs/2026-07-13-rag-quality-data-audit-handoff.md)

이 문서는 현재 유효한 구현 수준, 검증 근거, 외부 확인이 필요한 위험과 다음 우선순위를 관리한다. 과거 세션별 RED/GREEN 및 커밋 기록은 인수인계 문서에 유지한다.

## 1. 현재 결론

- 주제별 최신 공지, 출처, 추천 질문, 최근 공지를 제공하는 RAG 챗봇의 로컬 기능은 구현돼 있다.
- 원격 `main`의 5개 RAG 품질 결함 수정과 학과 게시판 50건 재수집을 보존하면서, 설정 기반 질문 의도·근거 정책과 데이터 감사를 통합했다.
- 고정 `data/evaluation/questions.json`을 변경하지 않고 local 평가 30/30을 유지한다.
- 최신 문서라도 질문의 연도·학기 또는 제목 marker·동의어 근거가 맞지 않으면 `grounded=false`로 거절하고 answer provider를 호출하지 않는다.
- 부분 수집 결과는 운영 원본이 아닌 `data/raw/candidates/`에 격리한다.
- 데이터 감사는 현재 게시글 50건에서 실제 데이터 경고 3건을 탐지한다.
- 백엔드 94개 테스트와 프론트엔드 9개 테스트, Ruff·TypeScript·ESLint·Next.js production build가 병합 결과에서 통과했다.
- SE 게시판은 `robots.txt`가 전체 자동 수집을 금지하므로 운영자 서면 허가 또는 승인된 공식 API 확보 전까지 자동 크롤링하지 않는다.
- 따라서 로컬 품질 통합은 완료됐지만 SE 데이터 권한, 오래된 개설강좌 자료, 졸업 자료, CI·운영 안전성 때문에 파일럿·운영 준비는 진행 중이다.

핵심 결정 3개:

1. 평가 기대값을 낮추지 않고 검색·근거 판정을 개선한다.
2. `topic_key`별 최신 1건 정책을 유지하되 기간 충돌과 제목 marker·동의어 적합성을 별도 검증한다.
3. robots.txt를 준수하며 부분 수집 후보, 평가 보고서, 감사 보고서를 운영 원본·Git 추적 파일과 분리한다.

## 2. 단계별 진행도

| 영역 | 상태 | 완료 근거 | 남은 조건 |
| --- | --- | --- | --- |
| 요구사항·설계 | 완료 | 품질·감사 설계와 Task 1~9 계획 | 정책 변경 시 문서 동시 갱신 |
| 백엔드 RAG | 로컬 완료 | 기간 충돌, 제목 근거, 일반 최신일 우선, provider 미호출 회귀 | OpenAI 운영 provider 재평가 |
| 데이터 수집 안전성 | 부분 완료 | 학과 50건, 부분 후보 격리, 원본 보호 테스트 | SE 운영자 허가 또는 공식 API |
| 데이터 감사 | 로컬 완료 | JSON·Markdown, exit 0/1/2, 원자적 저장, 본문 제외 | 현재 경고 3건 해결·승인 |
| 자동 평가 | 완료 | 고정 30문항 전체 통과, exit 0 | 데이터 변경 시 공식 원문 재검토 |
| 프론트엔드 | 완료 | 답변·출처·추천 질문·최근 공지, 9 tests, build | 페이지 fetch E2E·접근성 자동화 |
| 전체 회귀 | 통과 | backend 94, Ruff, frontend test/type/lint/build | CI 필수 검사 구성 |
| main 통합 | 완료 | 원격 선행 변경과 품질 브랜치 3-way 병합 및 충돌 회귀 통합 | 원격 push 후 확인 |
| 파일럿 준비 | 부분 완료 | 로컬 기능·평가 통과 | P0 데이터 검증과 P1 안전장치 |
| 운영 준비 | 미착수 | 계획만 존재 | 관측성·rate limit·backup·healthcheck |

## 3. 실행 스냅샷

| 항목 | 값 |
| --- | --- |
| provider | `local` |
| embedding | `local-hash-embedding-v1`, 1,536차원 |
| answer | `local-extractive-answer-v1` |
| retrieval | `top_k=5`, `min_score=0.09` |
| 저장 데이터 | 게시글 50건, `kumoh=50`, `seboard=0` |
| 게시일 범위 | 2024-09-04 ~ 2026-06-30 |
| 로컬 인덱스 | 청크 84개 |
| 자동 평가 | 30/30, exit 0 |
| 평가 세부 | topic 30/30, grounded 30/30, latest-only 30/30, source-title 11/11 |
| 데이터 감사 | 경고 3건, exit 1 |
| 생성 보고서 | `data/evaluation/reports/`, `data/audit/reports/`(Git 제외) |

## 4. 통합된 품질 정책

### 질문·근거 판정

- 질문에서 연도, 1·2학기, 계절학기, 최근성, 동의어와 특징어를 결정적으로 추출한다.
- 질문의 기간과 문서 제목이 충돌하면 최신 문서라도 근거에서 제외한다.
- 장학금 “신청”, 채용·초빙 등 제목 marker와 alias가 질문 표현에 연결되는지 확인한다.
- 일반 “최근 학과 공지”는 검색 점수보다 유효 게시일이 가장 최신인 URL을 우선한다.
- 설정 정책이 없는 기존 `TopicCatalog` 생성자에서도 기간 충돌, 채용·초빙, 일반 최신일의 기존 동작을 유지한다.
- 근거 게이트를 통과하지 못하면 `grounded=false`이며 answer provider를 호출하지 않는다.
- 답변은 출처 카드, 추천 질문, 최근 공지 순서로 표시한다.

### 데이터·보고서 안전성

- 정상 수집 결과만 `data/raw/posts.json`에 저장한다.
- `--allow-partial` 부분 결과는 `data/raw/candidates/posts-partial.json`에 저장한다.
- 평가와 감사의 JSON·Markdown 쌍은 공용 원자적 writer로 교체하고 실패 시 이전 보고서를 복구한다.
- 감사 보고서에는 게시글 본문, 비밀값, 로컬 절대 경로를 포함하지 않는다.
- 원본 게시글 또는 주제·근거 규칙 변경 후 `index --reset` → `evaluate` → `audit_data` 순서로 재검증한다.

## 5. 데이터 상태와 감사 경고

| 경고 코드 | 대상 | 현재 값 | 필요한 확인 |
| --- | --- | --- | --- |
| `missing_source` | `seboard` | 저장 게시글 0건 | 운영자 허가 또는 승인된 공식 API 확보 |
| `stale_topic` | `course_openings` | 최신 2025-08-07 | 실제 최신 개설강좌·수강신청 공지인지 공식 원문 확인 |
| `empty_topic` | `graduation` | 게시글 0건 | 졸업 공지의 승인된 공식 소스 또는 자료 부재 UX 결정 |

현재 주제별 저장 상태:

| 주제 | 건수 | 최신 게시일 |
| --- | ---: | --- |
| `general` | 15 | 2026-06-17 |
| `career` | 14 | 2026-06-30 |
| `registration` | 12 | 2026-06-16 |
| `scholarship` | 6 | 2026-06-17 |
| `capstone` | 2 | 2026-03-19 |
| `course_openings` | 1 | 2025-08-07 |
| `graduation` | 0 | 없음 |

“주제별 최신”은 저장 데이터 안에서의 최신을 뜻한다. 공식 사이트에 더 최신 자료가 있어도 수집되지 않으면 답변은 오래될 수 있으므로 날짜·원문 링크를 계속 노출하고 중요한 학사 결정은 원문 재확인을 안내한다.

### SE 게시판 수집 제한

- 2026-07-14 확인 기준 `https://seboard.site/robots.txt`는 `User-agent: *`, `Disallow: /`로 자동 수집을 금지한다.
- Cloudflare 콘텐츠 신호도 `ai-train=no`로 확인됐다.
- 운영자 서면 허가 또는 공개·승인된 `SEBOARD_API_URL`을 확보하기 전에는 Selenium/API 우회 수집을 시도하지 않는다.
- `missing_source=seboard` 경고는 허가 문제가 해결될 때까지 숨기지 않는다.

## 6. 병합 결과 검증 기록

2026-07-15 `main`에서 실행한 결과:

| 검증 | 결과 |
| --- | --- |
| 원격 동기화 | `origin/main`의 `0d766a9`까지 fast-forward 후 병합 |
| normative 평가 데이터 | 기능 브랜치에서 변경 없음 |
| RAG 충돌 집중 테스트 | 13 tests 통과 |
| 재인덱싱 | 50 posts, 84 chunks, exit 0 |
| 실제 local 평가 | 30 passed, 0 failed, exit 0 |
| backend pytest | 94 tests 통과 |
| backend Ruff | `All checks passed!` |
| frontend Vitest | 3 files, 9 tests 통과 |
| frontend TypeScript | exit 0 |
| frontend ESLint | exit 0 |
| Next.js production build | exit 0, 정적 페이지 4개 |
| 데이터 감사 | 50 posts, 3 issues, exit 1(의도된 품질 경고) |
| 생성물 ignore | Chroma·평가·감사·부분 후보 모두 제외 |

비차단 경고:

- Vitest가 Vite CJS Node API deprecation을 출력한다.
- 공식 SE 데이터와 OpenAI 운영 provider는 검증되지 않았다.

## 7. 남은 우선순위 TODO

### P0 — 외부 데이터 검증

| ID | 작업 | 완료 조건 |
| --- | --- | --- |
| P0-1 | SE 데이터 사용 권한 | 운영자 허가 또는 승인된 공식 API와 사용 범위 기록 |
| P0-2 | 원문 최신성 대조 | 주요 주제의 날짜·대상·신청 경로·canonical URL 확인 |
| P0-3 | 감사 경고 처리 | 경고 3건을 해결하거나 승인된 예외로 문서화 |
| P0-4 | 최신성 범위 확정 | 동시에 유효한 공지를 `topic_key` 1건 또는 문서 시리즈 단위로 처리할지 결정 |

### P1 — 다음 개발 프로젝트

| ID | 작업 | 완료 조건 |
| --- | --- | --- |
| P1-1 | backend line coverage 85%+ | SE fixture, OpenAI mock, provider factory, API endpoint, index/crawl CLI 보강 |
| P1-2 | 임베딩 fingerprint | provider·모델·차원·청킹·주제 규칙 불일치 시 재인덱싱 안내 |
| P1-3 | frontend 통합/E2E | fetch 성공·오류·추천 재질문과 390px/1280px 흐름 자동화 |
| P1-4 | GitHub CI | backend/frontend 검사와 production build가 PR을 차단 |

### P2 — 운영 안정성

- Docker healthcheck와 readiness 순서
- request ID, 선택 주제·출처·점수·지연시간을 포함한 민감정보 없는 관측성
- rate limit, 운영 CORS, provider timeout 및 오류 응답 표준화
- 증분 수집, 수정·삭제 감지, 인덱스 backup/restore
- 의존성 경고와 lockfile 재현성 정기 검토

## 8. 운영 검증 명령

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
backend/.venv/Scripts/python.exe -m ruff check backend
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate
backend/.venv/Scripts/python.exe -m backend.scripts.audit_data
npm --prefix frontend test
frontend/node_modules/.bin/tsc.cmd -p frontend/tsconfig.json --noEmit --incremental false
npm --prefix frontend run lint
npm --prefix frontend run build
```

감사는 경고가 있으면 exit 1을 반환한다. 현재 예상값은 평가 exit 0, 감사 exit 1과 위 3개 경고다.

## 9. 문서 유지 규칙

- 데이터 건수·최신일·평가 지표·테스트 수·브랜치 상태가 바뀌면 이 문서를 함께 갱신한다.
- 세션별 상세 이력은 handoff에, 현재 결론과 TODO는 이 문서에 기록한다.
- 로컬 코드 완료와 공식 사이트·운영 환경 검증 완료를 구분한다.
- 수치 없는 “완료” 대신 명령, exit code, 건수, 날짜로 근거를 남긴다.
- `.env`, API key, password, bearer token은 기록하지 않고 `민감정보 제거됨`으로 대체한다.
