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

- `schema_version`
- `generated_at` (UTC)
- 선택된 `provider`
- `embedding_model`, `embedding_dimensions`
- `chunk_size`, `chunk_overlap` 청킹 설정
- `collection` 이름(`CHROMA_COLLECTION`)
- `raw_posts_sha256`, `topic_rules_sha256`
- 저장된 `indexed_chunks` 수
- signature를 canonical JSON으로 해시한 `fingerprint`

manifest의 전체 필드는 `schema_version`, UTC `generated_at`, `provider`, `embedding_model`, `embedding_dimensions`, `chunk_size`, `chunk_overlap`, `collection`, `raw_posts_sha256`, `topic_rules_sha256`, `indexed_chunks`, `fingerprint`다. fingerprint가 포함하는 signature 필드는 schema version, collection, provider, embedding model/dimension, chunking 설정, raw posts SHA-256, topic rules SHA-256이며 `generated_at`과 `indexed_chunks`는 포함하지 않는다. `generated_at`은 manifest 생성 시각이자 호환 RAG service 세대의 generation identity/기록이고, `indexed_chunks`는 실제 Chroma count와 별도로 비교한다. `OPENAI_CHAT_MODEL`도 이 embedding signature에 포함되지 않는다.

현재 schema version은 `5`이다. v5는 v4의 `document_type` 계약에 `historical` 값을 추가해 과거 참고 문서를 공지·일반 정적 안내와 구분한다. v1~v4 manifest 또는 이 metadata 계약이 다른 과거 index는 호환되지 않는다.

API와 evaluation CLI는 요청·평가 시작 시 현재 설정과 파일을 사용해 signature를 다시 계산하고 manifest의 필드, content hash, 실제 Chroma chunk count를 비교한다. 하나라도 다르면 fail closed하며 provider를 호출하지 않는다. API는 채팅을 차단하고, 평가 CLI는 첫 질문 전에 실행 오류로 종료한다.

차원이 같아도 local hash와 OpenAI embedding은 같은 벡터 공간이 아니므로 호환되지 않는다. 다음 변경은 모두 provider-matched 전체 재인덱싱이 필요하다.

```powershell
backend/.venv/Scripts/python.exe -m backend.scripts.index --reset
```

- embedding provider 또는 effective embedding model
- `EMBEDDING_DIMENSIONS`
- `CHROMA_COLLECTION`
- `CHUNK_SIZE`, `CHUNK_OVERLAP` 설정값
- 원본 게시글 또는 `data/topic_rules.json`의 source/topic 규칙

`CHUNK_SIZE` 또는 `CHUNK_OVERLAP` 설정값을 바꾸면 signature mismatch가 발생해 API와 평가가 자동으로 fail closed한다. 반면 현재 정규화·청킹 알고리즘 구현 자체의 code hash/version은 signature에 자동 포함되지 않는다. 알고리즘 변경이 index의 의미를 바꾸면 maintainer가 `INDEX_SCHEMA_VERSION`과 `IndexSignature.schema_version`의 Pydantic `Literal[...]`/schema validation을 의도적으로 bump한 뒤 전체 재인덱싱해야 한다. 단순한 구현 변경만으로 자동 mismatch가 발생한다고 가정하지 않는다.

`OPENAI_CHAT_MODEL`만 변경하는 경우에는 기존 임베딩과 manifest signature가 유효하므로 재인덱싱하지 않는다. 다만 answer 품질·quota·실패율은 현재 provider와 데이터로 별도 평가한다. OpenAI로 전환할 때는 provider-matched reindex/evaluation을 수행하고 local에서 사용한 threshold를 그대로 가져오지 말고 별도로 calibration한다.
