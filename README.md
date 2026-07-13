# SE Mentor Bot

SE 게시판과 금오공과대학교 소프트웨어전공 공지사항의 공개 게시글 약 100건을 수집하고, 검색된 게시글만 근거로 답변하는 RAG 챗봇 프로토타입입니다. 답변에는 사용한 게시글의 제목·작성일·원문 링크와 함께 추천 질문·최근 공지가 표시됩니다.

전체 진행도·우선순위 TODO·검증 기준은 [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md), RAG 단계별 흐름과 변경 시 재인덱싱 기준은 [`docs/RAG_ARCHITECTURE.md`](docs/RAG_ARCHITECTURE.md)를 참고하세요.

## 구성

```text
frontend/              Next.js 채팅 UI
backend/app/           FastAPI, 크롤러, 청킹, RAG
backend/scripts/       수집·인덱싱 CLI
backend/tests/         pytest 단위 테스트
data/raw/              수집된 원본 JSON
data/evaluation/       평가 질문
data/topic_rules.json  주제·키워드·추천 질문 규칙
chroma_db/             로컬 벡터 인덱스(커밋 제외)
```

## 준비 사항

- Python 3.11~3.13
- Node.js 20.9 이상
- Chrome: SE 게시판 Selenium 수집 시 필요
- OpenAI API 키(선택): 키나 할당량이 없으면 로컬 모드 사용 가능

```powershell
Copy-Item .env.example .env
# AI_PROVIDER=auto는 키가 있으면 OpenAI, 없으면 로컬 모드를 선택합니다.
# 로컬 모드를 강제하려면 AI_PROVIDER=local로 설정합니다.

py -3.13 -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend install
```

OpenAI 모드는 Responses API와 Embeddings API를 사용합니다. 로컬 모드는 문자·단어 해시 벡터와 출처 기반 추출 답변을 사용해 API 비용 없이 실행됩니다. `AI_PROVIDER=local|openai|auto`로 선택합니다.

## 데이터 수집 및 인덱싱

```powershell
backend/.venv/Scripts/python -m backend.scripts.crawl --kumoh-limit 50 --seboard-limit 50
backend/.venv/Scripts/python -m backend.scripts.index --reset
```

`data/topic_rules.json`은 주제 키·표시명·분류 키워드·추천 질문을 관리하는 단일 유지보수 지점입니다. 인덱싱 시 제목과 본문을 이 규칙으로 분류하고, 같은 주제에서는 유효한 `published_at`이 가장 최신인 게시글만 답변 검색 대상으로 표시합니다. 게시일이 없거나 형식이 올바르지 않으면 `crawled_at`을 최신성 비교에 사용합니다.

원본 게시글이나 `data/topic_rules.json`을 변경한 뒤에는 위의 `--reset` 명령으로 전체 인덱스를 다시 만드세요. 그러지 않으면 이전 주제·최신성 metadata가 Chroma에 남을 수 있습니다. 온라인 검색은 `is_latest_topic=true`를 적용하므로 같은 주제의 이전 게시글은 답변 근거에서 제외됩니다.

SE 게시판은 JavaScript 기반이므로 기본적으로 Selenium을 사용합니다. 공개 JSON API를 확인한 경우 `.env`의 `SEBOARD_API_URL`에 주소를 지정하면 API 수집을 우선합니다. 한 소스가 일시적으로 실패해도 성공한 데이터를 점검하려면 `--allow-partial`을 추가합니다.

저장소의 `data/raw/posts.json`에는 크롤러 실사이트 검증을 위해 수집한 학과 게시글 46건이 포함되어 있습니다. 약 100건의 최종 데이터셋은 위 명령으로 두 소스를 다시 수집해 생성합니다.

수집 대상은 로그인 없는 공개 글로 제한합니다. 요청 간 기본 1초 간격을 유지하며, 운영 전 각 사이트의 이용정책과 `robots.txt`를 다시 확인하세요. 첨부파일은 이름과 링크만 저장하고 파일 본문은 분석하지 않습니다.

## 로컬 실행

터미널 1:

```powershell
backend/.venv/Scripts/python -m uvicorn backend.app.main:app --reload
```

터미널 2:

```powershell
npm --prefix frontend run dev
```

- 챗봇: <http://localhost:3000>
- API 상태: <http://localhost:8000/api/health>
- API 문서: <http://localhost:8000/docs>

인덱스가 비어 있으면 채팅 API는 `409`를 반환합니다. OpenAI 모드를 명시했는데 키가 없거나 할당량이 없으면 OpenAI 요청은 실패하므로 로컬 모드를 사용하세요.

## Docker 실행

`.env`를 만든 뒤 다음을 실행합니다.

```powershell
docker compose up --build
```

크롤링과 인덱싱은 로컬 명령으로 먼저 수행하고, 생성된 `data/`와 `chroma_db/`가 컨테이너에 마운트되도록 구성되어 있습니다.

## 검증

```powershell
backend/.venv/Scripts/python -m pytest backend/tests
backend/.venv/Scripts/python -m ruff check backend
backend/.venv/Scripts/python -m backend.scripts.index --reset
backend/.venv/Scripts/python -m backend.scripts.evaluate
npm --prefix frontend run lint
npm --prefix frontend run build
```

자동 평가는 외부 API 비용이 없는 local provider를 기본으로 사용하고 결과를 `data/evaluation/reports/latest.json`, `latest.md`에 저장합니다. 종료 코드 1은 측정된 품질 assertion 실패이며 보고서를 검토해야 한다는 뜻이고, 종료 코드 2는 입력·설정·인덱스 오류로 평가를 완료하지 못했다는 뜻입니다.

평가 시 `data/evaluation/questions.json`을 바탕으로 검색 Top-5 적중 여부, 출처 정확성, 주제 분류, 최신 게시글만 사용했는지, 데이터에 없는 질문의 답변 거절 여부를 기록합니다. 중요한 학사 결정은 항상 원문 공지를 재확인해야 합니다.
