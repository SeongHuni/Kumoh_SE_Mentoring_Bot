# RAG Providers

이 문서는 provider 선택, local/OpenAI 구현, 인덱스 호환성의 실제 runtime 동작을 설명한다. 지원 설정의 sample 값은 [`.env.example`](../../.env.example), 현재 상태는 [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md)를 기준으로 한다.

## Provider 선택

`AIProvider`는 `embed(texts)`와 `answer(question, contexts)` 두 메서드로 추상화된다. `provider_factory.py`가 `AI_PROVIDER`와 API key를 사용해 선택 provider를 계산한다.

| `AI_PROVIDER` | 선택 동작 |
| --- | --- |
| `local` | API key와 무관하게 local hash embedding과 extractive answer 사용 |
| `openai` | `OPENAI_API_KEY`가 없으면 설정 오류이며, OpenAI Embeddings API와 Responses API 사용 |
| `auto` | key가 있으면 OpenAI, 없으면 local로 선택 |

`auto`는 key의 quota나 네트워크 성공 여부를 시험하지 않는다. key는 있지만 quota가 없으면 local로 자동 복구하지 않고 OpenAI 오류가 발생할 수 있다. `.env.example`은 안전한 local sample이며, 애플리케이션 설정의 fallback은 `AI_PROVIDER=auto`다. 운영에서는 의도한 provider를 명시하고 provider-matched index/evaluation을 유지한다.

## Local provider

`LocalHashProvider`는 한국어·영문·숫자 token과 공백을 제거한 2~4글자 조각을 Blake2b로 벡터에 투영하고 L2 정규화한다. 제목 token과 제목 조각에는 별도 가중치를 주며, answer는 검색된 근거 문장에서 추출한다. 외부 모델·GPU·API 비용 없이 결정적이라는 장점이 있지만 동의어와 의미 이해에는 한계가 있다. local의 effective embedding model은 `local-hash-embedding-v1`, answer model은 `local-extractive-answer-v1`이다.

## OpenAI provider

`OpenAIProvider`는 문서를 batch로 OpenAI Embeddings API에 보내고, 답변은 Responses API의 `output_text`를 사용한다. 답변 prompt는 검색된 자료 밖의 추측을 금지하고 `[자료 N]` 근거 표기를 요구한다. 모델명과 차원은 설정에서 가져오며 API key, quota, 네트워크와 비용 관리가 필요하다.

## 실제 manifest 불변조건

인덱싱이 성공하면 `CHROMA_PATH/index-manifest.json`에 다음을 기록한다.

- 선택된 `provider`
- effective embedding model과 `embedding_dimensions`
- `chunk_size`, `chunk_overlap` 청킹 설정
- `collection` 이름(`CHROMA_COLLECTION`)
- `raw_posts_sha256`, `topic_rules_sha256`
- 저장된 `indexed_chunks` 수
- signature를 canonical JSON으로 해시한 `fingerprint`

fingerprint가 포함하는 signature는 schema version, collection, provider, embedding model/dimension, chunking 설정, raw posts SHA-256, topic rules SHA-256이다. `OPENAI_CHAT_MODEL`은 이 embedding signature에 포함되지 않는다.

API와 evaluation CLI는 요청·평가 시작 시 현재 설정과 파일을 사용해 signature를 다시 계산하고 manifest의 필드, content hash, 실제 Chroma chunk count를 비교한다. 하나라도 다르면 fail closed하며 provider를 호출하지 않는다. API는 채팅을 차단하고, 평가 CLI는 첫 질문 전에 실행 오류로 종료한다.

차원이 같아도 local hash와 OpenAI embedding은 같은 벡터 공간이 아니므로 호환되지 않는다. 다음 변경은 모두 provider-matched 전체 재인덱싱이 필요하다.

```powershell
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
```

- embedding provider 또는 effective embedding model
- `EMBEDDING_DIMENSIONS`
- `CHROMA_COLLECTION`
- `CHUNK_SIZE`, `CHUNK_OVERLAP`, 정규화·청킹 방식
- 원본 게시글 또는 `data/topic_rules.json`의 source/topic 규칙

`OPENAI_CHAT_MODEL`만 변경하는 경우에는 기존 임베딩과 manifest signature가 유효하므로 재인덱싱하지 않는다. 다만 answer 품질·quota·실패율은 현재 provider와 데이터로 별도 평가한다. OpenAI로 전환할 때는 provider-matched reindex/evaluation을 수행하고 local에서 사용한 threshold를 그대로 가져오지 말고 별도로 calibration한다.
