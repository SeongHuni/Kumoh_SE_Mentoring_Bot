# RAG 품질·데이터 감사 구현 인수인계

작성 시작: 2026-07-13
최종 갱신: 2026-07-15
상태: `main` 통합 검증 완료, 외부 데이터·운영 검증 대기

## 1. 다음 작업자 진입점

```powershell
Set-Location 'C:\Users\tjdgns\3-2_SummerSIG\Kumoh_SE_Mentoring_Bot'
git branch --show-current
git status --short
git log --oneline -15
```

예상 기준:

| 항목 | 값 |
| --- | --- |
| 브랜치 | `main` |
| 원격 선행 기준 | `0d766a9` |
| 통합 기능 기준 | `codex/rag-quality-hardening`의 `99422cf` |
| 저장 데이터 | 50 posts (`kumoh=50`, `seboard=0`) |
| 인덱스 | 84 chunks, local provider |
| 자동 평가 | 30/30, exit 0 |
| 데이터 감사 | 3 issues, exit 1 |
| backend/frontend | 94 tests / 9 tests |

`backend/.venv`가 없으면 README의 고정 requirements 명령으로 먼저 생성한다. 인덱스와 보고서는 Git에 포함되지 않으므로 새 환경에서는 재생성한다.

## 2. 기준 문서

- 설계: [`../specs/2026-07-13-rag-quality-data-audit-design.md`](../specs/2026-07-13-rag-quality-data-audit-design.md)
- 구현 계획: [`../plans/2026-07-13-rag-quality-data-audit-implementation.md`](../plans/2026-07-13-rag-quality-data-audit-implementation.md)
- 현재 프로젝트 상태: [`../../PROJECT_STATUS.md`](../../PROJECT_STATUS.md)
- 운영·평가 절차: [`../../rag/operations-evaluation.md`](../../rag/operations-evaluation.md)

## 3. 핵심 결정 3개

1. 고정 30문항 기대값을 약화하지 않고 검색·근거 판정을 수정한다.
2. `topic_key`별 최신 1건을 유지하되 질문·문서의 기간 충돌과 제목 marker·동의어 적합성을 검증한다.
3. robots.txt를 준수하고 부분 수집 후보·평가 보고서·감사 보고서를 운영 원본과 분리한다.

## 4. 구현 커밋 이력

| 커밋 | 범위 |
| --- | --- |
| `5bfd23b` | RAG 품질·데이터 감사 설계 |
| `93dd6d7` | Task 1~9 TDD 구현 계획 |
| `4093c94` | 검색 정책 모델 초기 구현 |
| `d63da19` | 주제 규칙 타입 엄격화 |
| `169e1c5` | 질문 의도 분석 |
| `1382579` | 기간·제목 근거 판정 |
| `b3acc91` | RAG 최신성·관련성 회귀 수정 |
| `91be420` | 부분 수집 후보 격리 |
| `d1b5ee8` | 공용 원자적 보고서 writer |
| `1451a49` | 데이터 감사 순수 계층 |
| `28e4e92` | 데이터 감사 CLI |
| `99422cf` | 운영·상태·인수인계 문서화 |

원격 `main`에는 작업 분기 후 다음 변경이 먼저 반영됐다.

| 커밋 | 범위 |
| --- | --- |
| `a2a0bdf` | 동일 5개 RAG 평가 결함을 로컬 rerank/grounding 방식으로 수정 |
| `0d766a9` | 학과 게시판 50건 재수집, SE robots.txt 제한 기록 |

## 5. main 병합 충돌 해결

충돌 파일은 `backend/app/rag.py`, `backend/tests/test_rag.py`, `docs/PROJECT_STATUS.md`였다.

### RAG 통합 원칙

- 원격 `main`의 기간 충돌, 채용·초빙 fallback, 일반 최신일 fallback을 유지했다.
- 기능 브랜치의 `QueryIntent`, `EvidencePolicy`, JSON marker·alias 정책을 우선 구조로 사용했다.
- 설정 정책이 없는 기존 `TopicCatalog` 생성자에는 최소 legacy fallback을 적용했다.
- 일반 최근 공지는 저장 게시글의 최신 URL을 우선하고, 게시글 목록이 없으면 검색 결과 게시일로 fallback한다.
- 두 브랜치의 독립 회귀를 합쳐 `test_rag.py` 13개 테스트로 검증했다.

### 데이터·문서 통합 원칙

- 원격의 50건 `data/raw/posts.json`을 그대로 보존했다.
- 46건 기준 문서 수치를 50건·84청크 기준으로 갱신했다.
- SE 게시판 자동 수집 금지와 감사 `missing_source` 경고를 함께 유지했다.

## 6. Task별 RED/GREEN 요약

| Task | RED | GREEN·커밋 |
| --- | --- | --- |
| 1 정책 모델 | 비문자열 key·배열 타입 허용 | 엄격 로딩, `d63da19` |
| 2 질문 의도 | module import 실패 | 연도·학기·최근성·alias parser, `169e1c5` |
| 3 근거 정책 | module import 실패 | 기간·제목 순수 판정, `1382579` |
| 4 RAG 회귀 | false-positive 3·false-negative 2 | 고정 평가 30/30, `b3acc91` |
| 5 부분 수집 | `main(argv)` 계약 부재 | 후보 경로 격리, `91be420` |
| 6 보고서 writer | 공용 module import 실패 | 쌍 교체·rollback, `d1b5ee8` |
| 7 감사 core | module import 실패 | source/topic 최신성 집계, `1451a49` |
| 8 감사 CLI | CLI import 실패 | JSON·Markdown·exit 0/1/2, `28e4e92` |
| 9 통합 검증 | 46건 기준 문서 | 원격 50건 데이터 기준 재검증·문서화 |

## 7. 최종 로컬 검증

2026-07-15 병합 결과:

- RAG 집중 테스트: 13 passed
- backend 전체: 94 tests passed
- Ruff: 통과
- frontend: 3 files, 9 tests passed
- TypeScript·ESLint·Next.js production build: exit 0
- 재인덱싱: 50 posts, 84 chunks, exit 0
- 자동 평가: 30/30, exit 0
- 세부 지표: topic 30/30, grounded 30/30, latest-only 30/30, source-title 11/11
- 데이터 감사: 50 posts, 3 issues, exit 1
- normative 평가 데이터: 기능 브랜치에서 변경 없음
- 생성 보고서: 본문·비밀값·로컬 절대 경로 없음, Git 제외

## 8. 현재 데이터 경고와 제한

| 코드 | 대상 | 의미 |
| --- | --- | --- |
| `missing_source` | `seboard` | robots.txt 금지로 저장 데이터 없음 |
| `stale_topic` | `course_openings` | 최신 게시일 2025-08-07 |
| `empty_topic` | `graduation` | 분류 게시글 없음 |

SE 게시판은 2026-07-14 확인 기준 `robots.txt`가 `Disallow: /`이고 Cloudflare 신호가 `ai-train=no`다. 운영자 서면 허가 또는 승인된 공식 API 없이 자동 수집을 재개하지 않는다.

## 9. 다음 개발 프로젝트

1. SE 데이터 사용 허가 또는 승인된 공식 API 확보.
2. 개설강좌 최신 원문과 졸업 자료의 승인된 공식 소스 확인.
3. backend line coverage 85% 이상: crawler fixture, OpenAI mock, provider factory, API endpoint.
4. embedding fingerprint로 모델·차원·청킹·규칙 불일치 인덱스 차단.
5. frontend fetch E2E·접근성, GitHub Actions 필수 검사.
6. 관측성, rate limit, healthcheck, backup/restore.

## 10. 재검증 명령

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

감사 exit 1은 현재 경고 3건에 대한 품질 신호다. 입력·설정 오류는 exit 2다.

민감정보는 기록하지 않는다. `.env`, API key, password, bearer token이 발견되면 `민감정보 제거됨`으로 대체한다.
