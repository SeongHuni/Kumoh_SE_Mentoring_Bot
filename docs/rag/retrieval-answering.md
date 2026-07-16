# RAG Retrieval And Answering

이 문서는 의도 확인, hybrid retrieval, 재정렬·관련성·최신성, 답변과 출처 계약을 설명한다. 변동 가능한 청크 수와 품질 snapshot은 [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md)에서 확인한다.

## 1. 의도 확인

`analyze_intents`는 질문을 topic으로 분류하고 `data/topic_rules.json`의 intent keyword를 기준으로 최대 3개 `IntentOption`을 정렬한다. 최초 요청에는 검색 대신 다음 형태의 `clarification`을 반환한다.

```json
{
  "response_type": "clarification",
  "answer": "질문 의도를 이렇게 이해했습니다. 무엇을 찾을지 선택해 주세요.",
  "grounded": false,
  "sources": [],
  "interpreted_intent": {"topic_key": "registration", "intent_key": "registration.main", "label": "...", "example": "..."},
  "clarification_options": []
}
```

사용자는 동일 질문과 선택한 `confirmed_intent_key`를 다시 보낸다. 이 key가 현재 분석 결과의 선택지에 없으면 검색하지 않고 clarification을 다시 반환한다. 따라서 임의의 다른 topic intent를 요청에 주입할 수 없다.

## 2. Query planning

확인된 intent 뒤에는 세 가지 query variant를 만든다.

1. 사용자의 원질문
2. 요청 연도·학기 + intent label + `공식 공지`를 조합한 deterministic rewrite
3. 공식 공지의 일정·신청 방법·유의사항을 가정한 HyDE 문장

세 variant는 BM25와 dense 검색에 동일하게 사용한다. local provider에서도 재현 가능해야 하므로 별도 LLM query rewrite 호출은 하지 않는다.

## 3. Hybrid retrieval와 RRF

`HybridRetriever`는 확인된 `topic_key`의 모든 청크를 대상으로 검색한다. `is_latest_topic=true`를 Chroma where 조건으로 사용하지 않는다. 과거 후보도 관련성 판정에 참여해야 하며, 최신성은 intent와 관련성이 확정된 뒤 적용한다.

- BM25는 NFKC/casefold token과 2~4글자 문자 조각, 인접 token 경계 조각을 사용한다.
- dense 검색은 각 query variant를 임베딩하고 Chroma cosine 결과를 합친다.
- 최종 표시 수보다 넓은 `max(RAG_TOP_K * 10, 50)` 후보를 두 검색기에 요청한다.
- 같은 chunk id의 metadata가 검색 경로마다 다르면 fail closed한다.
- lexical/dense 원점수의 규모가 다르므로 직접 더하지 않고 `1 / (60 + rank)`의 RRF를 합산한다.

`HybridCandidate.fused_score`는 RRF provenance를 다시 계산해 검증한다. forged score, 비정상 rank, NaN/inf는 거절한다.

## 4. Reranker와 CRAG식 관련성 판정

reranker는 다음 정보를 deterministic score와 hard conflict로 변환한다.

- 확인된 topic/intent metadata 일치
- intent keyword·evidence marker의 제목/본문 일치
- exclusion marker 충돌
- 질문에 명시된 연도·학기와 제목 또는 본문 metadata 충돌
- BM25와 dense 두 검색 신호의 존재

명시 intent metadata가 다르거나 title exclusion, 연도·학기 충돌이 있으면 점수가 높아도 제외한다. 관련성 gate는 다음처럼 보수적으로 동작한다.

- 정확한 marker와 lexical+dense 두 신호가 있으면 `relevant`
- title marker와 lexical 신호가 있으면 `relevant`
- 그 밖의 부족한 근거는 `ambiguous`
- intent/기간 충돌은 `irrelevant`

최종 답변에는 `relevant`만 사용한다. `ambiguous`를 낮은 신뢰 답변으로 전달하지 않는다.

## 5. 점수·최신성·구체 요청 근거

CRAG 통과 후보에 `RAG_MIN_SCORE`를 적용한 뒤 `select_freshest`가 같은 `intent_key`와 canonical URL을 묶어 최신 게시글을 선택한다.

- 파싱 가능한 `published_at`이 없는 후보는 “최근/최신” 질문에서 제외한다.
- 날짜가 있으면 가장 늦은 게시일을 우선한다.
- 동일 URL의 여러 청크는 가장 강한 청크 하나로 대표한다.
- 날짜 동률은 reranker/RRF 품질과 안정적인 chunk id로 결정한다.

그다음 broad intent(`career.general`, `scholarship.general`, `general.recent`)에서는 최신 글 자체가 사용자의 구체 요청어를 지지하는지 검사한다. 최신 글이 맞지 않으면 오래된 일치 문서로 후퇴하지 않고 `no_answer`를 반환한다. 이 순서는 “같은 intent에서는 최신 정보만 사용”이라는 정책을 보장한다.

예: `최근 취업 프로그램`에서 최신 career 글이 교원 초빙이고 과거에 프로그램 글이 있어도, 과거 글을 최신 프로그램처럼 제시하지 않는다.

## 6. Context compression과 답변

선택된 청크는 query match term, distinctive term, intent keyword/evidence marker와 겹치는 문장을 최대 3개 추출한다. 원래 순서를 복원하고 `id`, URL, source, published_at, score 등 metadata는 그대로 보존한다. 일치 문장이 없으면 원문 청크를 유지한다.

- local provider는 `확인된 공지`, 번호·제목·게시일, `핵심 내용`, 원문 재확인 안내로 답한다.
- OpenAI provider는 압축 context만 Responses API에 전달하고 자료 밖 추측을 금지한다.
- URL·제목·게시일·source는 모델이 만들지 않고 애플리케이션 metadata에서 구성한다.
- 같은 canonical URL은 source 카드에서 한 번만 표시한다.
- 최종 근거가 없으면 answer provider를 호출하지 않고 `response_type=no_answer`, `grounded=false`, 빈 `sources`를 반환한다.

답변 응답의 핵심 구조는 다음과 같다.

```json
{
  "response_type": "answer",
  "answer": "확인된 공지 ... [자료 1]",
  "sources": [{"title": "공지 제목", "url": "https://...", "source": "kumoh", "published_at": "2026-02-11", "score": 0.31}],
  "grounded": true,
  "interpreted_intent": {"topic_key": "registration", "intent_key": "registration.main", "label": "...", "example": "..."},
  "clarification_options": [],
  "suggested_questions": [],
  "recent_notices": []
}
```

## 7. 추천 질문과 최근 공지

`suggested_questions`는 확인된 topic의 질문을 먼저 제공하고 부족하면 general 추천으로 채운다. `recent_notices`는 확인 intent의 최신 글 1개, topic 최신 글, 다른 topic 최신 글 순으로 최대 3개를 중복 URL 없이 제공한다.

최근 공지는 답변 source가 아니라 별도 탐색 목록이다. frontend는 answer에서는 `최근 공지`, no-answer에서는 `답변 근거와 별개인 참고용 최근 공지`로 표시한다. 학사 정보는 시간이 지나면 무효가 될 수 있으므로 사용자는 source 카드의 원문과 게시일을 다시 확인해야 한다.
