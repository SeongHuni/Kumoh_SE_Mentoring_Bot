# RAG 품질·데이터 감사 구현 인수인계

작성 시작: 2026-07-13
최종 갱신: 2026-07-15
상태: 로컬 구현·통합 검증 완료, 원격 통합과 외부 데이터 검증 대기
브랜치: `codex/rag-quality-hardening`

## 1. 다음 작업자 진입점

기존 전용 worktree에서 이어간다. 새 worktree를 만들거나 루트 `main`의 미관련 변경을 섞지 않는다.

```powershell
Set-Location 'C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot\.worktrees\rag-quality-hardening'
git branch --show-current
git status --short
git log --oneline -12
git diff --stat main...HEAD
```

예상 상태:

| 항목 | 값 |
| --- | --- |
| 작업 브랜치 | `codex/rag-quality-hardening` |
| 로컬 기능 범위 | Task 1~9 완료 |
| 저장 데이터 | 46 posts (`kumoh=46`, `seboard=0`) |
| 인덱스 | 79 chunks, local provider |
| 자동 평가 | 30/30, exit 0 |
| 데이터 감사 | 3 issues, exit 1 |
| push/PR/main 병합 | 미수행 |

최초 재검증:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
backend/.venv/Scripts/python.exe -m ruff check backend
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate
backend/.venv/Scripts/python.exe -m backend.scripts.audit_data
```

감사 exit 1은 현재 데이터의 `missing_source`, `stale_topic`, `empty_topic` 경고를 뜻하며 실행 오류가 아니다. 입력 오류는 exit 2다.

## 2. 기준 문서

- 설계: [`../specs/2026-07-13-rag-quality-data-audit-design.md`](../specs/2026-07-13-rag-quality-data-audit-design.md)
- 구현 계획: [`../plans/2026-07-13-rag-quality-data-audit-implementation.md`](../plans/2026-07-13-rag-quality-data-audit-implementation.md)
- 현재 프로젝트 상태: [`../../PROJECT_STATUS.md`](../../PROJECT_STATUS.md)
- 운영·평가 절차: [`../../rag/operations-evaluation.md`](../../rag/operations-evaluation.md)

## 3. 핵심 결정 3개

1. `data/evaluation/questions.json`의 30개 normative expectation은 약화하거나 변경하지 않는다.
2. `topic_key`별 최신 1건 정책을 유지하되 질문·문서의 연도/학기 충돌과 제목 marker/동의어 적합성을 근거 게이트로 추가한다.
3. 부분 수집은 후보 경로, 평가·감사는 ignore된 보고서 경로를 사용해 운영 원본과 Git 추적 파일을 보호한다.

## 4. 구현 커밋

| 커밋 | 범위 |
| --- | --- |
| `5bfd23b` | RAG 품질·데이터 감사 설계 |
| `93dd6d7` | Task 1~9 TDD 구현 계획 |
| `4093c94` | Task 1 검색 정책 모델 초기 구현 |
| `a5b503c` | 중단 시점 인수인계 기록 |
| `d63da19` | Task 1 주제 규칙 키·배열 타입 엄격화 |
| `169e1c5` | Task 2 질문 의도 분석 |
| `1382579` | Task 3 기간·제목 근거 판정 |
| `b3acc91` | Task 4 RAG 최신성·관련성 회귀 수정 |
| `91be420` | Task 5 부분 수집 후보 격리 |
| `d1b5ee8` | Task 6 공용 원자적 보고서 writer |
| `1451a49` | Task 7 데이터 감사 순수 계층 |
| `28e4e92` | Task 8 데이터 감사 CLI |
| `docs: record rag quality hardening` | Task 9 상태·운영·인수인계 문서(이 문서를 포함한 HEAD) |

## 5. Task별 RED/GREEN 기록

### Task 1 — 검색 정책 설정 모델

- RED: 비문자열 topic/default key 두 사례가 허용되는 실패를 확인했다.
- GREEN: `_clean_key`와 문자열 배열 항목 타입 검증을 추가했다.
- 결과: 관련 테스트와 전체 backend 66 tests, Ruff 통과.
- 참고: 초기 구현의 명세 리뷰는 통과했다. 독립 코드 품질 리뷰가 중단되어 직접 diff 검토와 엄격 타입 회귀를 추가했다.

### Task 2 — 질문 의도 분석

- RED: `backend.app.query_intent` import 실패.
- GREEN: 연도·학기·최근성·alias·특징어를 추출하는 결정적 parser와 4 tests 통과.
- 전체 backend: 70 tests 통과.

### Task 3 — 근거 관련성 정책

- RED: `backend.app.evidence_policy` import 실패.
- GREEN: 기간 충돌과 제목 marker·특징어를 판정하는 순수 계층 5 tests 통과.
- 전체 backend: 75 tests 통과.

### Task 4 — RAG 연결과 품질 실패 5건

- RED: false-positive 3건(`registration-period`, `capstone-second-semester`, `scholarship-apply`)과 false-negative 2건(`career-recruitment`, `general-recent-department`)을 정확히 재현했다.
- GREEN: intent/evidence gate, 일반 최신 게시일 우선, 사람이 관리하는 marker·alias 규칙을 RAG에 연결했다.
- focused RAG 30 tests, 전체 backend 80 tests, Ruff 통과.
- 고정 평가셋은 변경하지 않았고 실제 local 평가가 30/30으로 개선됐다.

### Task 5 — 부분 수집 후보 격리

- RED: 기존 crawl `main(argv)` 계약 부재로 `TypeError` 확인.
- GREEN: 전체 성공만 운영 원본에 기록하고 부분 성공은 `data/raw/candidates/posts-partial.json`에 저장한다. 운영 원본과 후보 경로가 같으면 거절한다.
- focused 4 tests, 전체 backend 82 tests, Ruff 통과.

### Task 6 — 공용 원자적 보고서 writer

- RED: `backend.app.reporting` import 실패.
- GREEN: JSON·Markdown 쌍 교체, 실패 rollback, 기존 수동 `.bak` 보존을 공용 함수로 구현하고 평가 CLI를 전환했다.
- focused 12 tests, 전체 backend 84 tests, 실제 평가 30/30 통과.

### Task 7 — 데이터 감사 순수 계층

- RED: `backend.app.data_audit` import 실패.
- GREEN: source count, topic 최신일, 누락 소스, 오래된 주제, 빈 주제를 집계한다.
- focused 3 tests, 전체 backend 87 tests, Ruff 통과.
- JSON·Markdown 모델에 게시글 본문을 포함하지 않는 회귀를 고정했다.

### Task 8 — 데이터 감사 CLI

- RED: `backend.scripts.audit_data` import 실패.
- GREEN: JSON·Markdown 보고서와 exit 0/1/2 계약, 입력 오류 시 기존 보고서 보존을 구현했다.
- focused 6 tests(공용 writer 포함), 전체 backend 91 tests, Ruff 통과.
- 실제 감사: 46 posts, 3 issues, exit 1.

### Task 9 — 통합 검증과 문서화

- normative 평가 파일은 `main` 대비 변경 없음.
- 재인덱싱: 46 posts, 79 chunks, exit 0.
- 자동 평가: 30/30, exit 0.
- 세부 metric: topic 30/30, grounded 30/30, latest-only 30/30, source-title 11/11.
- backend 91 tests·Ruff 통과.
- frontend 3 files/9 tests·TypeScript·ESLint·Next.js production build 통과.
- Next.js build가 변경한 `frontend/next-env.d.ts`는 저장소 기준 내용으로 복구했다.
- README, 운영 문서, 프로젝트 상태, 이 인수인계를 실제 수치로 갱신했다.

## 6. 생성 보고서와 Git 안전성

| 생성물 | 경로 | Git |
| --- | --- | --- |
| Chroma 인덱스 | `chroma_db/` | 제외 |
| 자동 평가 | `data/evaluation/reports/latest.json`, `latest.md` | 제외 |
| 데이터 감사 | `data/audit/reports/latest.json`, `latest.md` | 제외 |
| 부분 수집 후보 | `data/raw/candidates/posts-partial.json` | 제외 |

감사 보고서 별도 스캔에서 비밀 패턴과 테스트용 비공개 본문이 검출되지 않았다. 테스트 소스에는 “본문이 보고서에 없어야 한다”는 픽스처가 의도적으로 존재하며 생성 보고서에는 포함되지 않는다.

## 7. 현재 데이터 경고

| 코드 | 대상 | 의미 |
| --- | --- | --- |
| `missing_source` | `seboard` | 저장 데이터에 SE 소스가 없음 |
| `stale_topic` | `course_openings` | 최신 게시일이 2025-08-07로 180일 기준 초과 |
| `empty_topic` | `graduation` | 분류된 게시글 없음 |

이 경고는 기대값을 삭제하거나 임계값을 임의로 낮춰 숨기지 않는다. 공식 사이트를 수집·대조한 후 원본과 규칙을 갱신하고 `index --reset` → `evaluate` → `audit_data` 순서로 재검증한다.

## 8. 외부 검증 대기

로컬 코드만으로 완료 처리하지 않은 항목:

- 학과·SE 공식 사이트의 live crawl 전체 성공
- 공식 원문 기준 최신 게시일, 대상, 신청 경로, canonical URL 수동 대조
- `course_openings` 2025-08-07이 실제 최신인지 확인
- 졸업 공지 자료 부재 또는 별도 소스 결정
- 실제 OpenAI provider에서 임계값·답변·비용·지연시간 재평가
- GitHub CI 필수 검사와 PR 독립 리뷰

독립 하위 에이전트 재리뷰는 2026-07-20까지의 도구 사용량 제한으로 실행하지 못했다. 이를 품질 통과로 간주하지 않으며, PR에서 사람 또는 사용 가능한 독립 에이전트의 diff 리뷰가 필요하다.

## 9. 다음 개발 프로젝트

1. backend line coverage 85% 이상: SE crawler fixture, OpenAI mock, provider factory, `/api/chat`·`/api/health`, index/crawl CLI.
2. embedding fingerprint: provider·모델·차원·청킹·주제 규칙 버전을 인덱스에 저장하고 불일치 사용 차단.
3. frontend page fetch E2E와 390px/1280px 접근성 회귀.
4. GitHub Actions로 backend/frontend 검증과 production build를 PR 필수 검사로 구성.

## 10. 인계 체크리스트

- [x] Task 1~8 기능·테스트 커밋 완료
- [x] 고정 30문항 불변과 local 30/30 확인
- [x] 부분 수집 운영 원본 보호 확인
- [x] 감사 보고서 본문·비밀값·절대경로 제외 확인
- [x] backend/frontend 전체 로컬 검증 통과
- [x] 현재 상태와 외부 검증 대기 분리 기록
- [ ] 기능 브랜치 push
- [ ] PR 생성 및 독립 리뷰
- [ ] main 병합 후 재검증
- [ ] 공식 사이트 live 데이터 감사

민감정보는 이 문서에 기록하지 않는다. `.env`, API key, password, bearer token이 발견되면 `민감정보 제거됨`으로 대체한다.
