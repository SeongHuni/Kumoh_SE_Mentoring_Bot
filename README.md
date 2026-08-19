# SE Mentor Bot

ChromaDB에 저장된 공지와 에브리타임 강의평을 검색해 답변하는 RAG 챗봇입니다.

## Requirements

- Python 3.12+
- Node.js 20+
- `chroma-data/` 디렉터리

`chroma-data/`에는 `sw_notice_d500` 컬렉션이 있어야 합니다. 이 컬렉션은
`text-embedding-3-small`, 청크 500, 오버랩 0으로 준비되어 있습니다.

## Setup

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
npm.cmd --prefix frontend ci
Copy-Item .env.example .env
```

`.env`에는 아래 네 항목만 설정합니다.

```env
EMBEDDING_API_KEY=
ANSWER_API_KEY=
EMBEDDING_MODEL=text-embedding-3-small
ANSWER_MODEL=gpt-4.1-mini
```

같은 OpenAI API 키를 `EMBEDDING_API_KEY`와 `ANSWER_API_KEY`에 모두 넣어도 됩니다.

## Run

터미널 두 개를 열어 실행합니다.

```powershell
.\run-backend.bat
```

```powershell
npm.cmd --prefix frontend run dev
```

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/api/health`
- API docs: `http://localhost:8000/docs`

## Retrieval

질문은 `text-embedding-3-small`으로 임베딩한 뒤 ChromaDB에서 검색합니다. 일반 질문은
카테고리 기반으로 후보를 좁힌 뒤 상위 5개 청크를 사용합니다. 교수·강의·수업 평가 질문은
`강의평` 카테고리를 우선 검색하며, 결과가 없을 때 전체 검색으로 돌아갑니다. 답변은 OpenAI
모델이 개조식으로 생성하고 출처 링크와 함께 표시됩니다.

## Verification

```powershell
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests
backend/.venv/Scripts/python.exe -m ruff check backend
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend test
```
