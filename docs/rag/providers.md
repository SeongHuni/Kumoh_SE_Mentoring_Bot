# RAG Providers

이 문서는 provider 선택, 로컬/OpenAI 구현, 인덱스 불변조건을 설명한다.

## Provider 선택

`AIProvider`는 `embed(texts)`와 `answer(question, contexts)` 두 메서드로 추상화된다. `provider_factory.py`가 다음 규칙으로 구현체를 선택한다.

| `AI_PROVIDER` | 동작 |
| --- | --- |
| `local` | API 키와 무관하게 로컬 해시/추출형 사용 |
| `openai` | `OPENAI_API_KEY` 필수 |
| `auto` | 키 문자열이 있으면 OpenAI, 없으면 로컬 |

주의: `auto`는 키의 할당량까지 시험하지 않는다. 키는 있으나 quota가 없으면 자동으로 로컬로 전환되지 않고 API 오류가 발생한다. 운영에서는 `local` 또는 `openai`를 명시하는 편이 안전하다.

## 로컬 임베딩

`LocalHashProvider`는 한국어·영문·숫자 토큰과 공백을 제거한 2~4글자 조각을 Blake2b로 1,536차원에 투영하고 L2 정규화한다.

- 일반 단어 가중치: `2.5`
- 문자 2/3/4-gram 가중치: `0.7 / 1.0 / 0.8`
- 제목 단어 가중치: `6.0`
- 제목 문자 조각 가중치: `2.0`

장점은 외부 모델, GPU, 다운로드, 비용이 없고 결과가 결정적이라는 점이다. 단점은 의미 유사성이 아니라 어휘 중복에 강하므로 동의어·의도 이해가 약하다는 점이다.

## OpenAI 임베딩·답변

`OpenAIProvider`는 문서를 64개씩 Embeddings API에 보내며 기본 모델은 `text-embedding-3-small`이다. 답변은 Responses API의 `output_text`를 사용한다. 프롬프트는 검색된 자료 밖의 추측 금지, 충돌 고지, 날짜 재확인, `[자료 N]` 표기를 요구한다.

OpenAI 경로는 더 자연스러운 종합 답변과 의미 검색에 유리하지만 API 키, quota, 네트워크, 비용 관리가 필요하다.

## 가장 중요한 인덱스 불변조건

문서 인덱싱과 질문 검색은 반드시 같은 provider·임베딩 모델·차원을 사용해야 한다. 로컬과 `text-embedding-3-small`은 모두 1,536차원일 수 있지만 벡터 의미는 완전히 다르다. 다음 값 중 하나라도 변경하면 반드시 실행한다.

```powershell
backend/.venv/Scripts/python -m backend.scripts.index --reset
```

- `AI_PROVIDER`
- `OPENAI_EMBEDDING_MODEL`
- 로컬 해시 feature 또는 가중치
- 임베딩 차원
- 청킹·정규화 방식
- 원본 게시글 집합

현재 Chroma 컬렉션은 embedding fingerprint를 검증하지 않는다. 추후 컬렉션 metadata에 provider, 모델, 차원, 청킹 버전을 저장하고 질의 시 불일치를 거부해야 한다.
