# SE Mentor Bot 프로젝트 상태와 다음 작업

> 기준일: 2026-07-15
> 작업 브랜치: `codex/rag-quality-hardening`
> 로컬 구현 기준: Task 1~8 커밋 완료, Task 9 통합 검증·문서화 완료
> 상세 이력: [`superpowers/handoffs/2026-07-13-rag-quality-data-audit-handoff.md`](superpowers/handoffs/2026-07-13-rag-quality-data-audit-handoff.md)

이 문서는 현재 유효한 구현 수준, 검증 근거, 외부 확인이 필요한 위험과 다음 우선순위를 관리한다. 과거 세션별 RED/GREEN 및 커밋 기록은 인수인계 문서에 유지한다.

## 1. 현재 결론

- 로컬 범위의 **RAG 품질 강화와 데이터 감사 Task 1~9는 완료**했다.
- 고정 평가 데이터 `data/evaluation/questions.json`을 변경하지 않고 local 평가를 25/30에서 30/30으로 개선했다.
- 최신 문서라도 질문의 연도·학기 또는 제목 근거가 맞지 않으면 `grounded=false`로 거절하고 provider 답변을 호출하지 않는다.
- 부분 수집 결과는 운영 원본이 아닌 `data/raw/candidates/`에 격리한다.
- 데이터 감사는 현재 게시글 46건에서 경고 3건을 탐지한다. 이는 코드 실패가 아니라 실제 데이터 보강이 필요하다는 품질 신호다.
- 백엔드 91개 테스트와 프론트엔드 9개 컴포넌트 테스트, 정적 검사 및 production build는 모두 통과했다.
- **공식 사이트 live 수집, 원문 최신성 대조, OpenAI 운영 provider, CI·배포 안전성은 아직 완료되지 않았다.** 따라서 로컬 품질 강화는 완료지만 파일럿·운영 준비는 진행 중이다.

핵심 결정 3개:

1. 평가 기대값을 낮추지 않고 검색·근거 판정을 수정한다.
2. `topic_key`별 최신 1건 정책은 유지하되 기간 충돌과 제목 marker·동의어 적합성을 별도 검증한다.
3. 부분 수집 후보, 자동 평가 보고서, 데이터 감사 보고서는 운영 원본·Git 추적 파일과 분리한다.

## 2. 단계별 진행도

| 영역 | 상태 | 완료 근거 | 남은 조건 |
| --- | --- | --- | --- |
| 요구사항·설계 | 완료 | 품질·감사 설계와 Task 1~9 구현 계획 | 정책 변경 시 동시 갱신 |
| 백엔드 RAG | 로컬 완료 | 기간 충돌, 제목 근거, 일반 최신일 우선, provider 미호출 회귀 | 공식 live 데이터·OpenAI 재평가 |
| 데이터 수집 안전성 | 로컬 완료 | 부분 결과 후보 경로 격리, 동일 경로 거절 테스트 | 학과·SE 두 소스 live 성공 |
| 데이터 감사 | 로컬 완료 | JSON·Markdown, exit 0/1/2, 원자적 저장, 본문 제외 | 현재 경고 3건 해결 |
| 자동 평가 | 완료 | 고정 30문항 전체 통과, exit 0 | 데이터 변경 시 원문 기준 재검토 |
| 프론트엔드 | 완료 | 답변·출처·추천 질문·최근 공지, 9 tests, build | 페이지 fetch E2E·접근성 자동화 |
| 전체 회귀 | 통과 | backend 91, Ruff, frontend test/type/lint/build | CI 필수 검사 구성 |
| 브랜치 통합 | 대기 | 기능별 로컬 커밋과 clean 검증 준비 | push·PR 리뷰·main 병합 |
| 파일럿 준비 | 부분 완료 | 로컬 기능·평가 통과 | P0 외부 데이터 검증과 P1 안전장치 |
| 운영 준비 | 미착수 | 계획만 존재 | 관측성·rate limit·backup·healthcheck |

## 3. 실행 스냅샷

| 항목 | 값 |
| --- | --- |
| provider | `local` |
| embedding | `local-hash-embedding-v1`, 1,536차원 |
| answer | `local-extractive-answer-v1` |
| retrieval | `top_k=5`, `min_score=0.09` |
| 저장 데이터 | 게시글 46건, `kumoh=46`, `seboard=0` |
| 로컬 인덱스 | 청크 79개 |
| 자동 평가 | 30/30, quality exit 0 |
| 평가 세부 | topic 30/30, grounded 30/30, latest-only 30/30, source-title 11/11 |
| 데이터 감사 | 경고 3건, quality exit 1 |
| 생성 보고서 | `data/evaluation/reports/`, `data/audit/reports/`(모두 Git 제외) |

## 4. 구현된 품질 정책

### 질문·근거 판정

- 질문에서 연도, 1·2학기, 최근성, 동의어와 특징어를 결정적으로 추출한다.
- 질문의 연도·학기와 문서 제목이 충돌하면 최신 문서라도 근거에서 제외한다.
- 장학금 “신청”, 채용·초빙 등 제목 marker와 alias가 질문 표현에 연결되는지 확인한다.
- 일반 “최근 학과 공지”는 검색 점수만이 아니라 유효 게시일이 가장 최신인 URL을 우선한다.
- 근거 게이트를 통과하지 못한 경우 `grounded=false`이며 answer provider를 호출하지 않는다.
- 답변은 출처 카드, 추천 질문, 최근 공지 순서로 표시해 읽기 흐름을 유지한다.

### 데이터·보고서 안전성

- 정상 수집 결과만 `data/raw/posts.json`에 저장한다.
- `--allow-partial` 부분 결과는 `data/raw/candidates/posts-partial.json`에 저장한다.
- 평가와 감사의 JSON·Markdown 쌍은 공용 원자적 writer로 교체하며 실패 시 기존 보고서를 복구한다.
- 감사 보고서에는 게시글 본문, 비밀값, 로컬 절대 경로를 포함하지 않는다.
- 원본 게시글 또는 주제·근거 규칙 변경 후 `index --reset`과 `evaluate`를 다시 실행한다.

## 5. 현재 데이터 감사

| 경고 코드 | 대상 | 현재 값 | 필요한 확인 |
| --- | --- | --- | --- |
| `missing_source` | `seboard` | 저장 게시글 0건 | 공식 SE 게시판 live crawl 성공과 URL 표본 대조 |
| `stale_topic` | `course_openings` | 최신 2025-08-07 | 실제 최신 개설강좌·수강신청 공지인지 공식 원문 확인 |
| `empty_topic` | `graduation` | 게시글 0건 | 졸업 공지 수집 또는 자료 부재 UX 정책 확정 |

현재 주제별 저장 상태:

| 주제 | 건수 | 최신 게시일 |
| --- | ---: | --- |
| `general` | 14 | 2026-06-17 |
| `career` | 13 | 2026-06-30 |
| `registration` | 12 | 2026-06-16 |
| `scholarship` | 5 | 2026-06-17 |
| `capstone` | 1 | 2026-03-19 |
| `course_openings` | 1 | 2025-08-07 |
| `graduation` | 0 | 없음 |

“주제별 최신”은 저장 데이터 안에서의 최신을 의미한다. 공식 사이트가 더 최신인데 수집되지 않았다면 답변도 오래될 수 있으므로, 날짜와 원문 링크를 사용자에게 계속 노출하고 중요한 학사 결정은 원문 재확인을 안내한다.

## 6. 검증 기록

2026-07-15 전용 worktree에서 실행한 결과:

| 검증 | 결과 |
| --- | --- |
| normative 평가 데이터 | `main` 대비 변경 없음 |
| 재인덱싱 | 46 posts, 79 chunks, exit 0 |
| 실제 local 평가 | 30 passed, 0 failed, exit 0 |
| backend pytest | 91 tests 통과 |
| backend Ruff | `All checks passed!` |
| frontend Vitest | 3 files, 9 tests 통과 |
| frontend TypeScript | exit 0 |
| frontend ESLint | exit 0 |
| Next.js production build | exit 0, 정적 페이지 4개 |
| 데이터 감사 | 46 posts, 3 issues, exit 1(의도된 품질 경고) |
| 감사 보고서 보안 검사 | 본문 픽스처·비밀 패턴 없음 |
| 생성물 ignore | Chroma·평가·감사·부분 후보 모두 제외 |

비차단 경고:

- Vitest가 Vite CJS Node API deprecation을 출력한다.
- 독립 하위 에이전트 재리뷰는 도구 계정 사용량 제한으로 실행하지 못했다. 로컬 자체 diff 검토와 전체 회귀는 완료했으며 PR에서 별도 사람/에이전트 리뷰가 필요하다.

## 7. 남은 우선순위 TODO

### P0 — 외부 데이터 검증

| ID | 작업 | 완료 조건 |
| --- | --- | --- |
| P0-1 | 학과·SE 공식 소스 재수집 | `--allow-partial` 없이 두 소스 성공, 소스별 건수·최신일 기록 |
| P0-2 | 원문 최신성 수동 대조 | 주요 주제의 날짜·대상·신청 경로·canonical URL을 공식 원문과 확인 |
| P0-3 | 감사 경고 해소 | `missing_source`, `stale_topic`, `empty_topic`을 해결하거나 승인된 예외로 문서화 |
| P0-4 | 최신성 범위 정책 확정 | 동시에 유효한 공지와 학기 변경을 `topic_key` 1건으로 처리할지 문서 시리즈 단위로 확정 |

### P1 — 다음 개발 프로젝트

| ID | 작업 | 완료 조건 |
| --- | --- | --- |
| P1-1 | 백엔드 line coverage 85%+ | SE crawler, OpenAI mock, provider factory, API endpoint, index/crawl CLI 보강 |
| P1-2 | 임베딩 fingerprint | provider·모델·차원·청킹·주제 규칙 버전 불일치 시 재인덱싱 오류 안내 |
| P1-3 | 프론트 통합/E2E | `page.tsx` fetch 성공·오류·추천 재질문과 390px/1280px 흐름 자동화 |
| P1-4 | GitHub CI | backend/frontend 검사와 production build가 PR을 차단 |

### P2 — 운영 안정성

- Docker healthcheck와 readiness 순서
- request ID, 선택 주제·출처·점수·지연시간을 포함한 민감정보 없는 관측성
- rate limit, 운영 CORS, provider timeout 및 오류 응답 표준화
- 증분 수집, 수정·삭제 감지, 인덱스 backup/restore
- 의존성 경고와 lockfile 재현성 정기 검토

## 8. 다음 작업자 진입점

```powershell
Set-Location 'C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot\.worktrees\rag-quality-hardening'
git branch --show-current
git status --short
git log --oneline -12
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate
backend/.venv/Scripts/python.exe -m backend.scripts.audit_data
```

예상 결과는 브랜치 `codex/rag-quality-hardening`, clean worktree, backend 91 tests 통과, 평가 exit 0, 감사 exit 1과 경고 3건이다. 기능 브랜치는 아직 push·PR·main 병합을 수행하지 않은 상태로 인계하며, 원격 작업 전 diff와 보안 검사를 다시 확인한다.

## 9. 문서 유지 규칙

- 데이터 건수·최신일·평가 지표·테스트 수·브랜치 상태가 바뀌면 이 문서를 함께 갱신한다.
- 세션별 상세 이력은 handoff에, 현재 결론과 TODO는 이 문서에 기록한다.
- 로컬 코드 완료와 공식 사이트·운영 환경 검증 완료를 구분한다.
- 수치 없는 “완료” 대신 명령, exit code, 건수, 날짜로 근거를 남긴다.
- `.env`, API key, password, bearer token은 문서에 기록하지 않고 `민감정보 제거됨`으로 대체한다.
