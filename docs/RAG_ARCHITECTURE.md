# SE Mentor Bot RAG Architecture

이 문서는 RAG 구현 문서의 진입점이다. 세부 내용은 유지보수 주제별로 나뉘며, 코드를 변경하기 전에 관련 문서와 `.env.example`을 함께 확인한다.

## 문서 우선순위

서로 다른 문서에서 값이나 상태가 다르게 보이면 다음 순서를 따른다.

1. 현재 건수, 준비도, 위험과 우선순위는 [`PROJECT_STATUS.md`](PROJECT_STATUS.md)를 단일 기준으로 사용한다.
2. 실행 명령은 [`rag/operations-evaluation.md`](rag/operations-evaluation.md)를 기준으로 한다.
3. 지원 설정과 sample 값은 [`.env.example`](../.env.example)을 기준으로 한다. `.env.example`의 안전한 local sample과 애플리케이션이 환경변수 없이 사용하는 fallback은 다를 수 있으며, 그 차이는 operations 문서에 설명한다.
4. 나머지 RAG 문서는 현재 구현의 안정적인 구조와 동작을 설명한다.
5. `docs/superpowers/**`와 `docs/reference/**`는 historical 자료이며 현재 상태나 실행 명령의 근거로 우선하지 않는다.

## 문서 구성

| 문서 | 다루는 내용 |
| --- | --- |
| [`PROJECT_STATUS.md`](PROJECT_STATUS.md) | 현재 진행도, 위험, 변동 가능한 수치와 검증 snapshot |
| [`rag/overview.md`](rag/overview.md) | 안정적인 전체 흐름과 아직 구현되지 않은 확장 우선순위 |
| [`rag/data-pipeline.md`](rag/data-pipeline.md) | 게시판 수집, 원본 스키마, 최신성, 정규화와 청킹 |
| [`rag/providers.md`](rag/providers.md) | provider 선택, 임베딩/답변 구현, manifest 불변조건 |
| [`rag/retrieval-answering.md`](rag/retrieval-answering.md) | Chroma 검색, 최신성 필터, 재정렬, 답변과 출처 |
| [`rag/operations-evaluation.md`](rag/operations-evaluation.md) | 환경변수, 운영 절차, health, 평가와 감사 |

## 빠른 판단 기준

- 임베딩 provider, 임베딩 모델 또는 임베딩 차원을 바꾸면 [`rag/providers.md`](rag/providers.md)를 갱신하고 provider가 일치하는 전체 재인덱싱을 한다.
- `OPENAI_CHAT_MODEL`처럼 답변 chat model만 바꾸면 임베딩 signature가 바뀌지 않으므로 재인덱싱하지 않는다. 답변 평가와 quota 검증은 별도로 한다.
- `CHROMA_COLLECTION`, `CHUNK_SIZE`/`CHUNK_OVERLAP` 설정값, 원본 source 집합 또는 `data/topic_rules.json`의 topic/source 규칙을 바꾸면 manifest signature mismatch로 자동 fail closed되므로 전체 재인덱싱을 한다.
- 현재 정규화·청킹 알고리즘 구현의 code hash/version은 signature에 자동 포함되지 않는다. 알고리즘이 index 의미를 바꾸면 maintainer가 `INDEX_SCHEMA_VERSION`과 `IndexSignature.schema_version`의 Pydantic `Literal[...]`/schema validation을 의도적으로 bump한 뒤 전체 재인덱싱한다. 단순 구현 변경만으로 자동 mismatch가 난다고 주장하지 않는다.
- 검색 점수, Top-K, threshold, 최신성 필터, 출처 카드 동작을 바꾸면 [`rag/retrieval-answering.md`](rag/retrieval-answering.md)를 갱신한다.
- 실행 명령, 지원 설정, 평가·감사 기준을 바꾸면 [`rag/operations-evaluation.md`](rag/operations-evaluation.md)를 갱신한다.

전체 재인덱싱 명령은 다음과 같다.

```powershell
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
```

질의와 평가는 현재 설정으로 manifest signature를 다시 계산해 일치 여부를 먼저 검사한다. 불일치한 인덱스에서는 provider를 호출하지 않고 fail closed한다.
