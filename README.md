# Department RAG Chatbot

RAG 방식의 학과 소개 멘토링 챗봇 기초 프로젝트입니다.

## 목적

1순위 사용자는 신입생, 예비 신입생, 복학생, 편입생입니다. 2순위 사용자는 재학생입니다.

## 지식 문서

지식 문서는 `data/knowledge/` 아래 주제별 Markdown 파일로 관리합니다.

- `department_intro.md`
- `curriculum.md`
- `professors.md`
- `graduation_requirements.md`
- `scholarships.md`
- `extracurricular_programs.md`
- `employment_status.md`
- `faq.md`
- `academic_notices.md`
- `department_events.md`

각 파일은 출처 URL, 마지막 확인일, 관리 메모, 검색 키워드를 포함합니다.

## 로컬 실행

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\uvicorn rag_chatbot.main:app --reload
```

API 확인:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/index/rebuild -Method Post
Invoke-RestMethod http://127.0.0.1:8000/chat -Method Post -ContentType "application/json" -Body '{"question":"학과 소개를 알려줘"}'
```

`/index/rebuild`는 `data/knowledge/`의 Markdown 시드 문서를 chunk로 나누고 Chroma 저장소에 인덱싱합니다. 초기 버전은 API 키 없이 검증 가능한 로컬 해시 임베딩을 사용합니다. 추후 OpenAI, Azure OpenAI, 또는 로컬 임베딩 모델로 `HashEmbeddingFunction`을 교체하면 됩니다.

## 테스트

```powershell
.\.venv\Scripts\pytest
```
