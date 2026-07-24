# 다음 작업자 진입점

> 마지막 갱신: 2026-07-24
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

현재 구현은 질문 의도 확인, query rewrite/HyDE, BM25+dense hybrid RRF, reranker, CRAG식 관련성 판정, intent별 날짜 최신성, 구체 요청 근거 판정, context compression, 출처·추천 질문·최근 공지 UI까지 연결되어 있다. 게시글은 멘토링 category와 `notice_kind`, 공지·정적 안내·역사 참고를 구분하는 `document_type`도 보존하며, `general.recent`는 category를 가로질러 최신 공식 공지만 찾는다. 현 수집 정책은 전공소개·교육목표·교육과정·주요성과·졸업 후 진로·비식별 교수·조교 소개·동아리명/소개 8개 정적 페이지로 한정되어 있고, 최신 8건이 canonical snapshot과 local provider의 schema v5 Chroma 16청크 인덱스에 반영되어 있다.

## 이번 작업에서 완료한 핵심

- `confirmed_intent_key`가 없는 첫 요청은 검색하지 않고 최대 3개의 의도 선택지를 반환한다.
- `registration.main`, `registration.change`, `registration.course_basket`, `registration.attendance`처럼 같은 topic 안의 하위 intent를 분리했다.
- BM25와 dense 검색을 넓은 후보군에 수행하고 RRF로 결합한다.
- deterministic reranker가 intent metadata, marker, 연도·학기 충돌을 검사한다.
- CRAG식 gate는 관련 문서만 통과시키며 ambiguous 문서는 답변에 사용하지 않는다.
- 최신성은 확인된 intent의 `published_at`을 사용한다. 최신 글이 세부 질문과 다르면 오래된 글로 후퇴하지 않는다.
- 답변 context는 관련 문장만 압축하고 metadata·canonical URL을 보존한다.
- frontend는 의도 선택, 중복 없는 재요청, 답변 시작 위치 자동 스크롤, 가독성 있는 줄바꿈, 출처·다음 질문·최근 공지를 제공한다.
- index schema를 v5로 올려 `document_type=historical`을 포함한 intent·category·notice metadata 계약이 다른 과거 인덱스를 거절한다. 정적 안내와 역사 참고 문서는 최신 공지 선택과 최근 공지 목록에 참여하지 않는다.
- 학과 사이트는 전공소개(`sub0101`)·교육목표(`sub0102`)·교육과정(`sub0105_2`)·주요성과(`sub0103`)·졸업 후 진로(`sub0104`)·비식별 교수소개(`sub0401`)·비식별 조교소개(`sub0402`)·동아리명/동아리 소개(`sub0504`)만 수집한다. 전공소개 페이지의 전공소개·교육목표·교육과정·연혁·오시는길 블록은 보존하되, 상세 교육목표·교육과정과 의미 중복을 제거한다. 주요성과와 졸업 후 진로는 `historical` 참고 문서로 저장한다. `KumohBoardCrawler`와 CLI의 게시판 옵션은 allowlist 밖이므로 거절한다. `--kumoh-static`은 이 8페이지를 수집한다. 교수·조교 이름·전화·이메일과 동아리 회장·부회장·연락처는 저장하지 않는다. 현재 8건을 canonical 원본으로 승격하고 local index에 16청크를 생성했다.

주요 구현 커밋은 `2a46123`(RAG orchestration), `a660368`(intent evaluation), `6701f61`(intent UI), `075f797`(stale broad-intent 거절), `94a540e`(답변 표시 UX)다. 문서 이후의 통합 상태는 커밋 해시를 추측하지 말고 위 `git` 명령으로 확인한다.

## 재현 명령

```powershell
$env:AI_PROVIDER="local"
# 현재 승인된 8건 canonical 원본 기준
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate --provider configured --minimum-cases 31
backend/.venv/Scripts/python.exe -m backend.scripts.audit_data --required-source kumoh

backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests --cov=backend.app --cov=backend.scripts --cov-config=backend/pyproject.toml --cov-report=term-missing
backend/.venv/Scripts/python.exe -m ruff check backend
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

2026-07-24 기록:

- backend: 462 passed, Ruff 통과 (의미 중복 제거·historical 문서·`llm_category` 정책 포함); coverage 93.82%는 이전 측정
- frontend: 6 files / 91 tests, typecheck·lint·build 통과
- evaluation (삭제 전 historical snapshot): 31/31, schema v4 84 chunks, exit 0; 현재 8건·16청크 기준 재평가 대기
- data audit: canonical 8건, `--required-source kumoh` 기준 `empty_topic` 10 warnings, exit 1
- production dependency audit: 0 vulnerabilities

Next build는 `frontend/next-env.d.ts`를 자동 변경할 수 있다. 생성 변경이 제품 변경이 아니라면 기존 저장소 형식으로 되돌리고 `git diff --check`를 확인한다.

## 다음 권장 작업

1. 현재 8건 canonical·16청크 local index의 topic/category 매핑을 검토한다. 정책이 바뀌기 전에는 SE·학과 게시판·기타 학과 페이지를 추가하지 않는다.
2. 현재 원본·인덱스 기준 평가 baseline과 회귀 질문을 만든다. 감사의 10개 `empty_topic` 경고는 정적 allowlist 범위 한계로 기록한다.
3. Docker가 있는 호스트에서 Compose build/start/health transition을 검증한다. 현재 호스트에는 Docker executable이 없다.
4. OpenAI provider를 사용할 경우 local 인덱스를 재사용하지 않는다. provider-matched reindex와 별도 threshold calibration이 선행 조건이다.
5. 390px 모바일과 다른 브라우저의 visual regression을 자동화한다.
6. 운영 telemetry, rate limit, Chroma backup/restore, 증분 ingestion을 별도 설계한다.

## 변경 금지선과 알려진 위험

- SE 게시판은 운영자 서면 허가 또는 승인된 공식 API가 문서화되기 전까지 `--seboard-limit 0`을 유지하며, 허가가 생겨도 현 allowlist 정책을 바꾸기 전에는 수집하지 않는다.
- 학과 사이트는 `sub0101`, `sub0102`, `sub0105_2`, `sub0103`, `sub0104`, `sub0401`, `sub0402`, `sub0504`만 수집한다. `sub0101`은 전공소개·교육목표·교육과정·연혁·오시는길의 본문 블록을 보존하고, `sub0103`·`sub0104`는 역사 참고 정보로만 보존한다. 학과 게시판과 나머지 학과 URL을 후보·canonical·인덱스에 복원하거나 추가하지 않는다.
- 금오공과대학교 학사안내 사이트(`www.kumoh.ac.kr/ko/sub06_01_*`)도 수집·저장하지 않는다. 이 URL 계열은 게시판·정적 안내 crawler 양쪽에서 거절하며, 현재 원본·후보·인덱스에는 관련 데이터가 없다.
- `audit_data`의 빈 topic 경고를 없애려고 allowlist 밖 데이터를 추가하지 않는다.
- 8건 canonical 원본은 허용 범위가 멘토링용 정적 페이지로 한정되어 10개의 `empty_topic` 경고가 난다. 이를 범위 한계로 명시한다.
- 삭제 전 평가 31/31은 역사 기록이며 현재 8건 static local snapshot의 회귀 통과가 아니다. 실시간 공식 사이트나 OpenAI 품질을 보증하지 않는다.
- 최근 공지는 답변 출처와 별도 보조 목록이다. 답변의 근거는 `sources`만 사용한다.
