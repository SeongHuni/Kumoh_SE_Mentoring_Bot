# RAG Retrieval And Answering

이 문서는 Vector Store, 검색·재정렬·필터링, 답변과 출처 구조를 설명한다.

## Vector Store 선택

현재 저장소는 로컬 영속형 Chroma이며 cosine 공간을 사용한다. 검색 점수는 우선 `1 - cosine_distance`로 변환한다.

| 선택지 | 적합한 상황 | 고려사항 |
| --- | --- | --- |
| Chroma | 로컬 프로토타입, 수백~수만 청크 | 배포·동시성·백업 기능 제한 |
| PostgreSQL + pgvector | 기존 PostgreSQL 운영 | 스키마·인덱스 운영 필요 |
| Qdrant/Weaviate | 독립 벡터 서비스 필요 | 추가 인프라 |
| OpenAI Vector Store | 관리형 검색을 선호 | 벤더 의존성과 비용 |

현재 79청크에서는 Chroma가 충분하다. 다중 서버, 사용자별 컬렉션, 대규모 증분 인덱싱이 필요해지면 pgvector 또는 전용 벡터 DB를 검토한다.

## 검색·재정렬·필터링

온라인 질의는 다음 순서다.

1. 질문을 현재 provider로 임베딩
2. Chroma cosine 검색으로 `RAG_TOP_K`개 조회
3. 질문의 2글자 이상 단어가 제목에 포함되면 단어당 `+0.08` 점수 보정
4. `RAG_MIN_SCORE`보다 낮은 결과 제거
5. 최고 점수의 75%보다 낮은 결과 제거
6. 결과가 없으면 LLM/provider를 호출하지 않고 `grounded=false` 반환

따라서 API의 `source.score`는 순수 cosine 점수가 아니라 제목 보정이 포함된 최종 랭킹 점수다. 제목 보정은 벡터 검색 Top-K 안에서만 적용되므로 Top-K 밖의 문서를 복구하지 못한다.

현재 운영 로컬 설정은 `top_k=5`, `min_score=0.09`다. `.env.example`의 `0.20`은 OpenAI 임베딩용 보수적 시작값이다. provider를 변경하면 평가 질문으로 임계값을 다시 튜닝한다.

향후 검색 품질 선택지:

- BM25 + vector hybrid 검색으로 정확한 과목명·약어 강화
- cross-encoder reranker로 Top-K 재정렬
- 게시일, 카테고리, source metadata 필터
- “최신”, “이번 학기” 질문에 시간 감쇠 적용
- query rewriting 또는 동의어 사전

## 답변과 출처

### 로컬 답변

질문 토큰과 겹치는 문장을 우선 선택하고 다음 문장까지 최대 360자로 추출한다. URL이 같은 청크는 한 번만 사용하며 최대 세 게시글을 `[자료 N]`으로 표시한다. 이는 요약·추론 모델이 아니므로 문장 연결이 어색할 수 있다.

### OpenAI 답변

필터된 청크 전체를 제목, 작성일, source와 함께 모델에 전달한다. 모델 답변과 별개로 API는 검색 결과 metadata에서 `sources`를 생성한다. 모델이 URL을 만들어 내게 하지 않고 애플리케이션이 canonical URL을 제공하는 구조다.

`ChatResponse`:

```json
{
  "answer": "... [자료 1]",
  "sources": [
    {
      "title": "공지 제목",
      "url": "https://...",
      "source": "kumoh",
      "published_at": "2026-03-19",
      "score": 0.31
    }
  ],
  "grounded": true
}
```

프론트엔드는 `sources`를 신뢰 가능한 링크 카드로 렌더링한다. 학사 정보는 시간이 지나면 무효가 될 수 있으므로 답변 끝에 원문·마감일 재확인을 안내한다.
