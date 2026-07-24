# SE Mentor Bot

학과 홈페이지 공지사항은 SE 게시판을 우선 source로 쓰는 정책에 따라 수집·저장하지 않는 정확도 우선 RAG 챗봇입니다. 현재 canonical 원본과 로컬 인덱스는 비어 있으며, 승인된 SE source 또는 검토 후보의 허용 문서를 승격·재인덱싱하기 전에는 채팅을 제공하지 않습니다. 첫 질문에서는 해석한 의도와 예시 선택지를 먼저 보여주고, 준비된 인덱스에서는 확인된 의도에 대한 근거만 답변에 사용합니다.

현재 수치·준비도·우선순위 TODO·검증 기준은 [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)를 기준으로 합니다. 다음 작업자는 [`docs/HANDOFF.md`](docs/HANDOFF.md)에서 시작하세요. RAG 단계별 흐름과 변경 시 재인덱싱 기준은 [`docs/RAG_ARCHITECTURE.md`](docs/RAG_ARCHITECTURE.md), 운영 명령과 평가 기준은 [`docs/rag/operations-evaluation.md`](docs/rag/operations-evaluation.md)를 참고하세요.

## 구성

```text
frontend/              Next.js 채팅 UI와 colocated Vitest 테스트
backend/app/           FastAPI, 크롤러, 청킹, RAG
backend/scripts/       수집·인덱싱·평가·데이터 감사 CLI
backend/tests/         pytest 단위·통합 테스트
data/raw/posts.json    현재 공식 소스 snapshot
data/evaluation/       평가 질문
data/audit/            데이터 품질 감사 입력·보고서(보고서는 커밋 제외)
data/topic_rules.json  주제·키워드·추천 질문 규칙
chroma_db/             로컬 벡터 DB와 index-manifest.json(커밋 제외)
docs/                  현재 상태·아키텍처·운영 문서
```

## 준비 사항

- Python 3.11~3.13
- Node.js `^20.19.0 || ^22.13.0 || >=24.0.0` (`frontend/package.json`의 `engines`와 동일)
- Selenium Python dependency: `backend/requirements-dev.txt`가 참조하는 `backend/requirements.txt`의 `selenium==4.45.0`이므로 기본 개발 설치에 포함되지만, 권한 확보 전에는 SE 수집 실행에 사용하지 않음
- Chrome/browser 준비와 실제 Selenium 수집 경로 실행: 운영자 서면 허가 범위가 문서화된 뒤에만 필요·허용되며, 승인된 공식 API 경로에는 Chrome이 필요하지 않음
- Docker 실행: Docker Desktop 또는 Docker Engine과 Compose plugin 필요
- OpenAI API 키(선택): 키나 할당량이 없으면 로컬 모드 사용 가능

```powershell
Copy-Item .env.example .env
# .env.example의 검증된 기본 sample은 AI_PROVIDER=local입니다.
# auto는 key가 있으면 OpenAI로 전환하므로 OpenAI 임계값 검증 전에는 사용하지 마세요.

py -3 -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
```

복사 직후의 검증된 기본 sample은 `AI_PROVIDER=local`입니다. `auto`는 키가 있으면 OpenAI로 전환하므로 OpenAI 임계값을 provider-matched index/evaluation으로 검증하기 전에는 사용하지 마세요. OpenAI 모드는 Responses API와 Embeddings API를 사용하고, 로컬 모드는 문자·단어 해시 벡터와 출처 기반 추출 답변을 사용해 API 비용 없이 실행됩니다. 지원 값은 `AI_PROVIDER=local|openai|auto`이며, `openai` 또는 `auto`로 전환하기 전 provider별 index/evaluation과 threshold 설정을 완료하세요.

## 데이터 수집 및 인덱싱

현재 학과 홈페이지 수집 범위는 정적 6페이지로 한정합니다: 전공소개(`sub0101`), 교육목표(`sub0102`), 교육과정(`sub0105_2`), 졸업 후 진로(`sub0104`, 역사 참고 정보), 비식별 교수소개(`sub0401`), 학생활동의 동아리명·동아리 소개(`sub0504`). 전공소개에서는 해당 섹션만 보존하고 교육목표·교육과정 상세 페이지와 의미가 겹치는 문장을 제거합니다. 주요성과(`sub0103`)는 수상·성과 제외 정책에 따라, 학과 게시판 전체와 그 밖의 학과 페이지는 crawler가 정책상 거절합니다. 일반 공지사항(`sub0601`)은 SE 게시판 우선 source 정책으로, 금오공과대학교 학사안내 사이트(`www.kumoh.ac.kr/ko/sub06_01_*`)는 별도 URL 차단 정책으로 수집·저장하지 않습니다.

```powershell
backend/.venv/Scripts/python.exe -m backend.scripts.crawl --kumoh-static --candidate-output data/raw/candidates/kumoh-community-2024.json --seboard-limit 0
```

`--kumoh-limit`, `--kumoh-all`, `--kumoh-all-boards`는 학과 게시판 수집을 재개할 수 없도록 오류로 종료합니다. 허용 범위를 검토 후보로 다시 수집할 때는 `--kumoh-static`만 사용합니다. 교수소개에서는 이름·전화·이메일을 제거하고 소속·전공 분야만 보존합니다. 동아리 페이지에서는 회장·부회장 등 개인 식별 정보와 이미지·연락처를 제외하며, 각 동아리의 이름과 소개만 보존합니다.

```powershell
backend/.venv/Scripts/python.exe -m backend.scripts.crawl --kumoh-static --candidate-output data/raw/candidates/kumoh-allowlist.json --seboard-limit 0
```

후보의 source·canonical URL·게시일·본문 범위를 검토한 뒤에만 `data/raw/posts.json`으로 승격하고, 이후 전체 재인덱싱·평가·감사를 실행한다.

SE 게시판 수집은 현재 비활성화되어 있습니다. 2026-07-14 확인 기준 `seboard.site/robots.txt`가 `User-agent: * / Disallow: /`로 전체 자동 수집을 금지하고 있습니다. `--seboard-limit`에 양수를 지정하려면 운영자 서면 허가 또는 승인된 공식 API 사용 승인이 먼저 있어야 하며, CLI에도 `--seboard-permission-confirmed`를 함께 지정해야 합니다. 이 flag는 운영자가 권한을 확인했다는 의사를 기록할 뿐, 실제 권한을 대신하지 않습니다. 승인된 공식 API 경로에서는 `SEBOARD_API_URL`을 사용하고 Chrome이 필요하지 않습니다. 서면 허가 범위가 문서화된 뒤 승인된 Selenium 경로를 선택할 때만 Chrome/browser를 준비하고 Selenium 수집을 실행하세요. 로그인 우회, CAPTCHA 무력화, 접근제어 회피는 범위 밖입니다.

한 소스가 일시적으로 실패해도 성공한 데이터를 점검하려면 `--allow-partial`을 추가합니다. 이때 부분 결과는 `data/raw/candidates/posts-partial.json`에만 저장되며 운영 원본 `data/raw/posts.json`을 덮어쓰지 않습니다. 후보를 운영 원본으로 승격하려면 소스·날짜·URL을 검토한 뒤 별도로 반영하고 전체 재인덱싱하세요.

외부 SE 데이터의 `llm_category`는 허용된 10개 category label 중 하나로 검증한 뒤 `category_key`·`category_label`로 정규화합니다. URL·게시일 등 canonical source 필드는 별도로 검증합니다.

`data/topic_rules.json`은 검색용 topic·하위 intent뿐 아니라 멘토링 업무 `category_key`와 `notice_kind`를 관리하는 단일 유지보수 지점입니다. category는 수업, 학적·졸업, 장학금, 취업·진로, 비교과·행사, 연구·캡스톤, 대학원, 학생회, 행정·안내, 기타로 구분합니다. 인덱싱 시 제목의 구체 키워드를 먼저 판정하고, 제목에 구체어가 없을 때만 제목 표기 marker를 사용합니다. 본문 보조 분류는 같은 문장·문단에 topic과 업무 action이 함께 있을 때만 허용해 우연한 본문 언급을 막습니다. 공지·정적 안내·역사 참고 문서는 `document_type`을 포함한 intent·category·notice kind metadata와 함께 보존합니다. `신청·모집`, `행사`, `제도`처럼 성격이 분명한 질의는 호환되는 notice kind만 근거로 남기며, 단순 `공지` 질의는 지나치게 좁히지 않습니다. 온라인 질의에서는 관련성 판정 후 같은 intent의 `published_at`이 가장 최신인 공지 근거를 선택합니다. `static`과 `historical` 문서는 최근 공지 목록과 최신성 경쟁에서 제외하며, 역사 참고 청크는 현재 수치·현황이 아니라는 경고를 포함합니다. 최신 intent 글이 사용자의 세부 요청과 맞지 않으면 이전 유사 글로 후퇴하지 않고 근거 없음으로 답합니다.

온라인 검색은 확인된 topic의 과거·현재 후보를 BM25와 dense 검색으로 넓게 수집한 뒤 RRF, intent-aware reranker, CRAG식 관련성 판정, 점수 gate를 적용합니다. `general.recent`만은 분류 카테고리를 가로질러 전체 공식 공지를 탐색하고, 이름을 명시한 공지는 최신성보다 직접 근거를 우선합니다. 그 밖의 intent는 같은 intent의 최신 게시글을 날짜로 확정하고, 최신 글이 질문의 구체 요청어를 직접 지지하는지 검사합니다. 답변은 최종 근거의 제목·작성일·canonical URL을 출처로 표시하고, 해당 주제의 추천 질문과 별도 최근 공지 목록을 함께 제공합니다. 수집 대상은 로그인 없는 공개 글로 제한하며 요청 간 기본 1초 간격을 유지하고, 운영 전 각 사이트의 이용정책과 `robots.txt`를 다시 확인합니다. 첨부파일은 이름과 링크만 저장하고 파일 본문은 분석하지 않습니다.

인덱싱이 성공하면 `chroma_db/index-manifest.json`에 provider·임베딩 모델·차원·청킹 설정·원본 게시글·주제 규칙의 fingerprint와 청크 수가 기록됩니다. 서버는 현재 설정·데이터와 manifest를 비교하고 하나라도 다르면 채팅을 차단합니다.

임베딩 provider·임베딩 모델·`EMBEDDING_DIMENSIONS`·`CHUNK_SIZE`·`CHUNK_OVERLAP`·`CHROMA_COLLECTION`·원본 게시글·`data/topic_rules.json`을 변경하면 `index --reset`으로 전체 인덱스를 다시 만드세요. 이 변경들은 index manifest fingerprint에 포함됩니다. `OPENAI_CHAT_MODEL`처럼 답변 chat model만 변경하는 경우에는 임베딩 signature가 달라지지 않으므로 재인덱싱이 필요하지 않습니다.

`data/raw/posts.json`의 현재 건수와 평가·감사 결과는 변동 가능한 운영 상태이므로 [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)의 실행 snapshot을 기준으로 확인하세요. 중요한 학사 결정은 표시된 원문 링크를 다시 확인해야 합니다.

## 로컬 실행

터미널 1:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn backend.app.main:app --reload
```

터미널 2:

```powershell
npm --prefix frontend run dev
```

- 챗봇: <http://localhost:3000>
- `/api/live`: 프로세스 liveness 확인
- `/api/health`: 인덱스와 provider를 포함한 RAG readiness 확인
- API 문서: <http://localhost:8000/docs>

첫 질문의 정상 응답은 답변이 아니라 `response_type=clarification`일 수 있습니다. UI에서 의도 선택지를 누르면 동일 질문과 `confirmed_intent_key`를 다시 보내며, 확인된 intent가 현재 질문의 선택지와 일치할 때만 검색합니다.

`/api/health`의 `status`는 다음처럼 해석합니다.

| 상태 | 의미와 조치 |
| --- | --- |
| `ready` | 현재 설정·데이터와 인덱스가 일치해 채팅 가능 |
| `needs_configuration` | OpenAI provider에 필요한 키가 없음 |
| `needs_index` | 인덱스가 비어 있으므로 `index --reset` 필요 |
| `needs_reindex` | manifest가 없거나 설정·데이터·청크 수가 달라 전체 재인덱싱 필요 |
| `unavailable` | 벡터 저장소를 열 수 없어 경로·권한·저장소 상태 점검 필요 |

채팅 API는 비어 있거나 오래된 인덱스에 `409`, provider 설정 또는 저장소 문제에 `503`, OpenAI 호출 실패에 `502`를 반환합니다. OpenAI 키나 할당량이 없으면 로컬 모드를 사용하세요.

## Docker 실행

`.env`를 만든 뒤 다음을 실행합니다. Docker Desktop 또는 Docker Engine과 Compose plugin이 필요합니다. 현재 검증 호스트에는 Docker가 설치되어 있지 않아 Compose runtime 검증은 남아 있지만, Docker가 설치된 환경에서는 아래 명령을 그대로 사용할 수 있습니다.

```powershell
docker compose up --build
```

Compose의 frontend `NEXT_PUBLIC_API_URL`은 Docker build-time에 이미지에 삽입됩니다. 값을 바꾸면 frontend image를 다시 build해야 하며, 실행 중 환경변수만 바꾸어서는 이미 빌드된 UI의 API 주소가 바뀌지 않습니다. Compose healthcheck는 startup ordering과 상태 보고를 돕지만 unhealthy 컨테이너의 자동 복구를 보장하지 않습니다.

크롤링과 인덱싱은 로컬 명령으로 먼저 수행하고, 생성된 `data/`와 `chroma_db/`가 컨테이너에 마운트되도록 구성되어 있습니다. backend healthcheck는 `/api/live`, frontend healthcheck는 frontend HTTP 응답을 확인합니다.

## 검증

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests --cov=backend.app --cov=backend.scripts --cov-config=backend/pyproject.toml --cov-report=term-missing
backend/.venv/Scripts/python.exe -m ruff check backend
$env:AI_PROVIDER="local"
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate --provider configured --minimum-cases 31
backend/.venv/Scripts/python.exe -m backend.scripts.audit_data
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
Push-Location frontend
npm audit --omit=dev
npm audit
Pop-Location
```

provider-matched local 평가의 핵심 순서는 `AI_PROVIDER=local` 설정, 같은 설정으로 `index --reset`, `--provider configured --minimum-cases 31` 평가입니다. 평가 CLI는 현재 설정과 strict index manifest가 맞는지 먼저 확인하므로 provider·임베딩 모델·차원·데이터·청킹이 어긋나면 평가를 완료하지 못합니다. `data/evaluation/questions.json`의 최소 케이스 수와 현재 통과 수치는 [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)를 기준으로 하며, 데이터/provider 변경 뒤에는 현재 31문항 이상을 다시 평가하세요.

자동 평가는 topic·확인 intent·응답 intent 일치, source의 공식 원문 연결, 최신 URL, 출처 제목, 근거 유무와 범위 밖 질문 거절을 기록합니다. `general.recent`는 카테고리별 최신 intent source를 허용하며, 이름을 명시한 직접 조회는 latest-only 검사를 적용하지 않을 수 있습니다. 종료 코드 1은 측정된 품질 assertion 실패이며 보고서를 검토해야 한다는 뜻이고, 종료 코드 2는 입력·설정·인덱스 오류로 평가를 완료하지 못했다는 뜻입니다. 중요한 학사 결정은 항상 원문 공지를 재확인해야 합니다.

데이터 감사는 소스 누락, 오래된 주제, 빈 주제를 검사하고 `data/audit/reports/latest.json`, `latest.md`를 생성합니다. exit 0은 경고 없음, exit 1은 품질 경고 존재, exit 2는 입력·설정 오류입니다. 현재 데이터의 감사 경고와 평가 세부 수치는 변동 가능하므로 PROJECT_STATUS와 생성 보고서를 함께 확인하세요. 보고서와 벡터 인덱스는 Git에 포함하지 않습니다.
