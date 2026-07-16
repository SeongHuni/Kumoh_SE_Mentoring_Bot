# 다음 작업자 진입점

> 마지막 갱신: 2026-07-16
>
> 상태 기준: [`PROJECT_STATUS.md`](PROJECT_STATUS.md)
>
> 실행 기준: [`rag/operations-evaluation.md`](rag/operations-evaluation.md)

## 먼저 확인할 것

```powershell
git status -sb
git log --oneline -12
Get-Content docs/PROJECT_STATUS.md -Encoding utf8
```

현재 구현은 질문 의도 확인, query rewrite/HyDE, BM25+dense hybrid RRF, reranker, CRAG식 관련성 판정, intent별 날짜 최신성, 구체 요청 근거 판정, context compression, 출처·추천 질문·최근 공지 UI까지 연결되어 있다. 로컬 canonical snapshot은 50 posts / 84 chunks이며 평가 31/31을 통과했다.

## 이번 작업에서 완료한 핵심

- `confirmed_intent_key`가 없는 첫 요청은 검색하지 않고 최대 3개의 의도 선택지를 반환한다.
- `registration.main`, `registration.change`, `registration.course_basket`, `registration.attendance`처럼 같은 topic 안의 하위 intent를 분리했다.
- BM25와 dense 검색을 넓은 후보군에 수행하고 RRF로 결합한다.
- deterministic reranker가 intent metadata, marker, 연도·학기 충돌을 검사한다.
- CRAG식 gate는 관련 문서만 통과시키며 ambiguous 문서는 답변에 사용하지 않는다.
- 최신성은 확인된 intent의 `published_at`을 사용한다. 최신 글이 세부 질문과 다르면 오래된 글로 후퇴하지 않는다.
- 답변 context는 관련 문장만 압축하고 metadata·canonical URL을 보존한다.
- frontend는 의도 선택, 중복 없는 재요청, 답변 시작 위치 자동 스크롤, 가독성 있는 줄바꿈, 출처·다음 질문·최근 공지를 제공한다.
- index schema를 v2로 올려 intent metadata가 없는 과거 인덱스를 거절한다.

주요 구현 커밋은 `2a46123`(RAG orchestration), `a660368`(intent evaluation), `6701f61`(intent UI), `075f797`(stale broad-intent 거절), `94a540e`(답변 표시 UX)다. 문서 이후의 통합 상태는 커밋 해시를 추측하지 말고 위 `git` 명령으로 확인한다.

## 재현 명령

```powershell
$env:AI_PROVIDER="local"
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate --provider configured --minimum-cases 31
backend/.venv/Scripts/python.exe -m backend.scripts.audit_data

backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests --cov=backend.app --cov=backend.scripts --cov-config=backend/pyproject.toml --cov-report=term-missing
backend/.venv/Scripts/python.exe -m ruff check backend
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

2026-07-16 결과:

- backend: 406 passed, coverage 93.86%, Ruff 통과
- frontend: 6 files / 90 tests, typecheck·lint·build 통과
- evaluation: 31/31, 84 chunks, exit 0
- data audit: 3 warnings, exit 1
- production dependency audit: 0 vulnerabilities

Next build는 `frontend/next-env.d.ts`를 자동 변경할 수 있다. 생성 변경이 제품 변경이 아니라면 기존 저장소 형식으로 되돌리고 `git diff --check`를 확인한다.

## 다음 권장 작업

1. `course_openings`와 `graduation`의 승인된 공식 원문을 추가한다. 원본만 넣지 말고 topic/intent 규칙, index schema 필요성, 31건 이상 평가를 함께 갱신한다.
2. Docker가 있는 호스트에서 Compose build/start/health transition을 검증한다. 현재 호스트에는 Docker executable이 없다.
3. OpenAI provider를 사용할 경우 local 인덱스를 재사용하지 않는다. provider-matched reindex와 별도 threshold calibration이 선행 조건이다.
4. 390px 모바일과 다른 브라우저의 visual regression을 자동화한다.
5. 운영 telemetry, rate limit, Chroma backup/restore, 증분 ingestion을 별도 설계한다.

## 변경 금지선과 알려진 위험

- SE 게시판은 운영자 서면 허가 또는 승인된 공식 API가 문서화되기 전까지 `--seboard-limit 0`을 유지한다.
- `audit_data`의 SE missing-source 경고를 없애려고 비승인 데이터를 추가하지 않는다.
- `course_openings`·`graduation` 질문은 직접 근거가 없으므로 현재 `no_answer`가 정상이다.
- 평가 31/31은 현재 local snapshot의 회귀 통과이며 실시간 공식 사이트나 OpenAI 품질을 보증하지 않는다.
- 최근 공지는 답변 출처와 별도 보조 목록이다. 답변의 근거는 `sources`만 사용한다.
