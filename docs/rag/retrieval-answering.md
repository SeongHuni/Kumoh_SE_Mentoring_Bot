# RAG Retrieval And Answering

이 문서는 Vector Store, 검색·재정렬·최신성 필터, 답변과 출처 구조를 설명한다. 변동 가능한 청크 수와 품질 snapshot은 [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md)에서만 확인한다.

## Vector Store

현재 구현은 local single-user prototype에 맞춘 영속형 Chroma이며 cosine 공간을 사용한다. 현재 prototype 규모에서는 Chroma가 충분하다. 다중 서버, 사용자별 collection, 큰 규모의 증분 인덱싱이나 운영 백업 요구가 생기면 pgvector 또는 독립 vector DB를 검토한다.

검색 결과 score는 Chroma cosine distance를 `1 - distance`로 바꾸고 0~1 범위로 제한한 값이다.

| 선택지 | 적합한 상황 | 고려사항 |
| --- | --- | --- |
| Chroma | local prototype, single-user 영속 검색 | 동시성·백업·분산 운영은 별도 설계 필요 |
| PostgreSQL + pgvector | 기존 PostgreSQL 운영과 결합 | schema·index 운영 필요 |
| Qdrant/Weaviate | 독립 vector service 필요 | 추가 인프라와 운영비 |
| OpenAI Vector Store | 관리형 검색 선호 | vendor 의존성과 비용 |

## 검색 순서

온라인 질의는 strict manifest 검사를 통과한 뒤 다음 순서로 처리한다.

1. 질문을 `data/topic_rules.json`으로 주제와 query intent로 분류한다.
2. 현재 선택 provider로 질문을 임베딩한다.
3. 모든 주제 검색은 `is_latest_topic=true`를 Chroma `where`에 적용한다. 구체 주제는 `topic_key=<분류 주제>`도 함께 적용한다.
4. `general` 주제의 일반 질문은 모든 주제의 최신 게시글을 대상으로 `RAG_TOP_K`개를 조회한다. “최근/최신” 의도가 있는 general 질문은 저장된 최신 게시글 URL로 범위를 더 좁힌다.
5. 질문의 2글자 이상 표현과 topic policy marker가 제목에 맞으면 제목·정책 점수를 보정해 재정렬한다.
6. 근거 정책이 연도·학기·용어 충돌이나 marker 불일치를 발견하면 해당 문서를 제외한다.
7. `RAG_MIN_SCORE` 절대 임계값과 최고 점수의 상대 임계값을 적용한다. 일반 최신성 질의는 선택된 최신 문서라는 정책 근거를 별도로 인정할 수 있다.
8. 유효한 결과가 없으면 answer provider를 호출하지 않고 `grounded=false`와 안내 문장을 반환한다.

구체 주제의 Chroma 조건은 다음과 같다.

```json
{
  "$and": [
    {"is_latest_topic": true},
    {"topic_key": "course_openings"}
  ]
}
```

제목 보정이 적용된 뒤의 `source.score`는 순수 cosine score가 아니라 최종 랭킹 score다. 보정은 vector search로 가져온 Top-K 안에서만 적용되며 Top-K 밖의 문서를 복구하지 않는다.

## 날짜 기반 최신성

인덱싱 전 `enrich_posts`가 각 게시글을 topic rule로 분류하고 `is_latest_topic`을 계산한다. 최신성 비교는 같은 `topic_key` 안에서 다음과 같이 동작한다.

- 파싱 가능한 `published_at`이 있는 게시글이 유효한 게시일이 없는 게시글보다 우선한다.
- 유효한 게시일끼리는 더 늦은 `published_at`이 최신이다.
- `published_at`이 없거나 ISO 형식으로 파싱되지 않는 게시글은 `crawled_at`을 비교값으로 사용한다.
- 같은 게시일이면 `crawled_at`이 마지막 tie-breaker다.

선택된 게시글에서 나온 모든 청크에 `is_latest_topic=true`가 복사된다. 이전 게시글은 raw snapshot과 Chroma에 보존될 수 있지만 온라인 주제 검색의 where filter에서 제외된다. 데이터가 저장된 snapshot보다 공식 사이트에서 더 최신일 수 있다는 문제는 이 필터가 해결하지 않으므로 답변의 canonical URL과 날짜를 원문에서 재확인해야 한다.

## 답변과 출처

최종 결과가 있으면 선택된 contexts만 answer provider에 전달한다.

- local answer는 질문 token과 겹치는 근거 문장을 중심으로 추출한다.
- OpenAI answer는 제목·작성일·source·본문을 Responses API에 전달하고, 모델이 URL을 만들지 않도록 애플리케이션이 metadata에서 출처를 만든다.
- 같은 canonical URL의 청크는 source 카드에서 한 번만 표시한다.
- `sources`의 URL·제목·작성일·source·score는 Chroma metadata에서 만들며, `grounded`는 실제 근거 통과 여부를 나타낸다.
- `suggested_questions`는 주제 규칙에서, `recent_notices`는 최신 topic 게시글에서 만든다. 근거가 없어도 두 보조 필드는 제공될 수 있다.

`ChatResponse`의 핵심 구조는 다음과 같다.

```json
{
  "answer": "... [자료 1]",
  "sources": [{"title": "공지 제목", "url": "https://...", "source": "kumoh", "published_at": "2026-03-19", "score": 0.31}],
  "grounded": true,
  "suggested_questions": ["이번 학기 개설강좌를 알려줘"],
  "recent_notices": []
}
```

학사 정보는 시간이 지나면 무효가 될 수 있으므로 답변에는 표시된 원문과 마감일을 다시 확인하라는 안내가 필요하다.
