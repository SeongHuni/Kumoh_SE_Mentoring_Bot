# SE Mentor Bot

현재 추적 스냅샷의 금오공과대학교 소프트웨어전공 공식 공지 50건만 검색하며, 검색된 게시글만 근거로 답변하는 RAG 챗봇 프로토타입입니다. 답변에는 사용한 게시글의 제목·작성일·원문 링크와 함께 추천 질문·최근 공지가 표시됩니다. SE 게시판 데이터는 운영자 허가 또는 승인된 공식 API가 확보되기 전까지 제공하지 않습니다.

현재 수치·준비도·우선순위 TODO·검증 기준은 [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)를 기준으로 합니다. RAG 단계별 흐름과 변경 시 재인덱싱 기준은 [`docs/RAG_ARCHITECTURE.md`](docs/RAG_ARCHITECTURE.md), 운영 명령과 평가 기준은 [`docs/rag/operations-evaluation.md`](docs/rag/operations-evaluation.md)를 참고하세요.

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
- OpenAI API 키(선택): 키나 할당량이 없으면 로컬 모드 사용 가능

```powershell
Copy-Item .env.example .env
# AI_PROVIDER=auto는 키가 있으면 OpenAI, 없으면 로컬 모드를 선택합니다.
# 로컬 모드를 강제하려면 AI_PROVIDER=local로 설정합니다.

py -3 -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
```

OpenAI 모드는 Responses API와 Embeddings API를 사용합니다. 로컬 모드는 문자·단어 해시 벡터와 출처 기반 추출 답변을 사용해 API 비용 없이 실행됩니다. `AI_PROVIDER=local|openai|auto`로 선택합니다.

## 데이터 수집 및 인덱싱

현재 허용된 수집 경로는 금오공대 소프트웨어전공 공식 공지 snapshot입니다.

```powershell
backend/.venv/Scripts/python.exe -m backend.scripts.crawl --kumoh-limit 50 --seboard-limit 0
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
```

SE 게시판 수집은 현재 비활성화되어 있습니다. 2026-07-14 확인 기준 `seboard.site/robots.txt`가 `User-agent: * / Disallow: /`로 전체 자동 수집을 금지하고 있습니다. `--seboard-limit`에 양수를 지정하려면 운영자 서면 허가 또는 승인된 공식 API 사용 승인이 먼저 있어야 하며, CLI에도 `--seboard-permission-confirmed`를 함께 지정해야 합니다. 이 flag는 운영자가 권한을 확인했다는 의사를 기록할 뿐, 실제 권한을 대신하지 않습니다. 승인된 공식 API 경로에서는 `SEBOARD_API_URL`을 사용하고 Chrome이 필요하지 않습니다. 서면 허가 범위가 문서화된 뒤 승인된 Selenium 경로를 선택할 때만 Chrome/browser를 준비하고 Selenium 수집을 실행하세요. 로그인 우회, CAPTCHA 무력화, 접근제어 회피는 범위 밖입니다.

한 소스가 일시적으로 실패해도 성공한 데이터를 점검하려면 `--allow-partial`을 추가합니다. 이때 부분 결과는 `data/raw/candidates/posts-partial.json`에만 저장되며 운영 원본 `data/raw/posts.json`을 덮어쓰지 않습니다. 후보를 운영 원본으로 승격하려면 소스·날짜·URL을 검토한 뒤 별도로 반영하고 전체 재인덱싱하세요.

`data/topic_rules.json`은 주제 키·표시명·분류 키워드·추천 질문·근거 규칙을 관리하는 단일 유지보수 지점입니다. 인덱싱 시 제목과 본문을 이 규칙으로 분류하고, 같은 주제에서는 유효한 `published_at`이 가장 최신인 게시글만 답변 검색 대상으로 표시합니다. 게시일이 없거나 형식이 올바르지 않으면 `crawled_at`을 최신성 비교에 사용합니다. 따라서 최신성은 수집 시점이 아니라 게시일을 우선하는 날짜 기반 동작이며, 저장 snapshot보다 공식 사이트에 더 최신 자료가 있을 가능성은 별도로 확인해야 합니다.

온라인 검색은 `is_latest_topic=true`를 적용하므로 같은 주제의 이전 게시글은 답변 근거에서 제외됩니다. 답변은 검색된 근거의 제목·작성일·canonical URL을 출처로 표시하고, 해당 주제의 추천 질문과 최근 공지를 함께 제공합니다. 수집 대상은 로그인 없는 공개 글로 제한하며 요청 간 기본 1초 간격을 유지하고, 운영 전 각 사이트의 이용정책과 `robots.txt`를 다시 확인합니다. 첨부파일은 이름과 링크만 저장하고 파일 본문은 분석하지 않습니다.

인덱싱이 성공하면 `chroma_db/index-manifest.json`에 provider·임베딩 모델·차원·청킹 설정·원본 게시글·주제 규칙의 fingerprint와 청크 수가 기록됩니다. 서버는 현재 설정·데이터와 manifest를 비교하고 하나라도 다르면 채팅을 차단합니다.

임베딩 provider·임베딩 모델·`EMBEDDING_DIMENSIONS`·`CHUNK_SIZE`·`CHUNK_OVERLAP`·원본 게시글·`data/topic_rules.json`을 변경하면 `index --reset`으로 전체 인덱스를 다시 만드세요. 이 변경들은 index manifest fingerprint에 포함됩니다. `OPENAI_CHAT_MODEL`처럼 답변 chat model만 변경하는 경우에는 임베딩 signature가 달라지지 않으므로 재인덱싱이 필요하지 않습니다.

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

`.env`를 만든 뒤 다음을 실행합니다.

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
backend/.venv/Scripts/python.exe -m backend.scripts.evaluate --provider configured
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

provider-matched local 평가의 핵심 순서는 `AI_PROVIDER=local` 설정, 같은 설정으로 `index --reset`, `--provider configured` 평가입니다. 평가 CLI는 현재 설정과 strict index manifest가 맞는지 먼저 확인하므로 provider·임베딩 모델·차원·데이터·청킹이 어긋나면 평가를 완료하지 못합니다. `data/evaluation/questions.json`의 최소 케이스 수와 현재 통과 수치는 [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)를 기준으로 하며, 데이터/provider 변경 뒤에는 최소 30문항을 다시 평가하세요.

자동 평가는 검색 Top-5 적중 여부, 출처 정확성, 주제 분류, 최신 게시글만 사용했는지, 데이터에 없는 질문의 답변 거절 여부를 기록합니다. 종료 코드 1은 측정된 품질 assertion 실패이며 보고서를 검토해야 한다는 뜻이고, 종료 코드 2는 입력·설정·인덱스 오류로 평가를 완료하지 못했다는 뜻입니다. 중요한 학사 결정은 항상 원문 공지를 재확인해야 합니다.

데이터 감사는 소스 누락, 오래된 주제, 빈 주제를 검사하고 `data/audit/reports/latest.json`, `latest.md`를 생성합니다. exit 0은 경고 없음, exit 1은 품질 경고 존재, exit 2는 입력·설정 오류입니다. 현재 데이터의 감사 경고와 평가 세부 수치는 변동 가능하므로 PROJECT_STATUS와 생성 보고서를 함께 확인하세요. 보고서와 벡터 인덱스는 Git에 포함하지 않습니다.
