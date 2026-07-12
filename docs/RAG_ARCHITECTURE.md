# SE Mentor Bot RAG Architecture

이 문서는 RAG 구현 문서의 진입점이다. 세부 내용은 유지보수 주제별로 분리되어 있으며, 코드를 변경하기 전에 관련 문서와 `.env.example`을 함께 확인한다.

## 문서 구성

| 문서 | 다루는 내용 |
| --- | --- |
| [`rag/overview.md`](rag/overview.md) | 현재 운영 상태, 전체 데이터 흐름, 확장 우선순위 |
| [`rag/data-pipeline.md`](rag/data-pipeline.md) | 게시판 수집, 원본 스키마, 정규화와 청킹 |
| [`rag/providers.md`](rag/providers.md) | `AI_PROVIDER`, 로컬/OpenAI provider, 임베딩 불변조건 |
| [`rag/retrieval-answering.md`](rag/retrieval-answering.md) | Vector Store, 검색·재정렬·필터링, 답변과 출처 |
| [`rag/operations-evaluation.md`](rag/operations-evaluation.md) | 환경변수, 운영 절차, 테스트와 평가 |

## 빠른 판단 기준

- 데이터 소스나 크롤러를 바꾸면 [`rag/data-pipeline.md`](rag/data-pipeline.md)를 수정한다.
- 주제·키워드·추천 질문을 바꾸면 `data/topic_rules.json`을 수정하고 전체 인덱스를 재생성한다.
- 임베딩 모델, provider, 벡터 차원, API 모델을 바꾸면 [`rag/providers.md`](rag/providers.md)를 수정하고 인덱스를 재생성한다.
- 검색 점수, Top-K, threshold, 출처 카드 동작을 바꾸면 [`rag/retrieval-answering.md`](rag/retrieval-answering.md)를 수정한다.
- 실행 명령, 환경변수, 평가 기준을 바꾸면 [`rag/operations-evaluation.md`](rag/operations-evaluation.md)를 수정한다.

## 재인덱싱이 필요한 변경

다음 값 중 하나라도 변경하면 반드시 전체 인덱스를 재생성한다.

```powershell
backend/.venv/Scripts/python -m backend.scripts.index --reset
```

- `AI_PROVIDER`
- `OPENAI_EMBEDDING_MODEL`
- 로컬 해시 feature 또는 가중치
- 임베딩 차원
- 청킹·정규화 방식
- 원본 게시글 집합
- `data/topic_rules.json`의 주제·키워드
