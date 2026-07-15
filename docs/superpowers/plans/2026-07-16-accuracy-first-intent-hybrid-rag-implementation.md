# Accuracy-First Intent Confirmation And Hybrid RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모든 자유 질문의 의도를 먼저 확인하고 BM25·Dense 합의 검색과 CRAG 관련성 판정 뒤에 세부 의도별 최신 문서를 선택하는 정확도 우선 RAG를 구현한다.

**Architecture:** topic catalog에 세부 intent 규칙을 추가하고, 의도 확인·query planning·lexical retrieval·rank fusion·rerank·relevance gate·freshness·compression을 작은 모듈로 분리한다. `RAGService`는 이 모듈을 조정하며, 프론트엔드는 clarification 응답을 선택 UI로 표시하고 확정 intent를 다시 전송한다.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, ChromaDB, pytest, Next.js 15, React 19, TypeScript, Vitest, Testing Library

---

## 파일 구조

### 새 백엔드 파일

- `backend/app/intent_analysis.py`: 자유 질문의 intent 후보 생성과 확정 intent 검증
- `backend/app/query_planner.py`: 원문·재작성·결정적 HyDE 검색문 생성
- `backend/app/lexical_retriever.py`: in-memory Okapi BM25
- `backend/app/hybrid_retriever.py`: Dense·BM25 후보와 RRF 합의 정보 결합
- `backend/app/reranker.py`: intent·marker·시간 조건 feature 기반 재정렬
- `backend/app/relevance_gate.py`: relevant·ambiguous·irrelevant 판정
- `backend/app/freshness_selector.py`: 관련 후보 안에서 intent별 최신 문서 선택
- `backend/app/context_compressor.py`: 근거 문장 추출과 metadata 보존

### 새 프론트엔드 파일

- `frontend/app/components/IntentClarification.tsx`: 질문 의도 선택 UI
- `frontend/app/components/IntentClarification.test.tsx`: 접근성·선택 동작 테스트

### 주요 수정 파일

- `data/topic_rules.json`: 세부 intent 규칙과 marker 선언
- `backend/app/topic_rules.py`: intent catalog parsing과 분류
- `backend/app/domain.py`: `intent_key` metadata
- `backend/app/topic_classifier.py`: title-first topic·intent enrichment
- `backend/app/chunking.py`: intent metadata 전달
- `backend/app/vector_store.py`: intent metadata 저장과 lexical corpus 조회
- `backend/app/schemas.py`: clarification request·response 계약
- `backend/app/rag.py`: 새 파이프라인 조정
- `backend/app/main.py`: confirmed intent 전달
- `backend/app/evaluation.py`: 평가 case의 confirmed intent 지원
- `frontend/app/lib/chatApi.ts`: 새 payload·response 검증
- `frontend/app/page.tsx`: clarification 선택 후 재요청
- `frontend/app/components/ChatMessage.tsx`: clarification과 참고용 최근 공지 구분
- `frontend/app/components/types.ts`: intent UI 타입
- `frontend/app/globals.css`: clarification 스타일
- `README.md`, `docs/rag/*.md`, `docs/PROJECT_STATUS.md`: 실제 동작과 검증 결과

---

### Task 1: 세부 Intent Catalog와 게시글 Metadata

**Files:**
- Modify: `backend/app/topic_rules.py`
- Modify: `backend/app/domain.py`
- Modify: `backend/app/topic_classifier.py`
- Modify: `backend/app/chunking.py`
- Modify: `backend/app/vector_store.py`
- Modify: `data/topic_rules.json`
- Test: `backend/tests/test_topic_rules.py`
- Test: `backend/tests/test_topic_classifier.py`
- Test: `backend/tests/test_chunking.py`
- Test: `backend/tests/test_vector_store.py`

- [ ] **Step 1: intent schema와 title-first 분류의 실패 테스트 작성**

```python
def test_catalog_classifies_registration_subintents() -> None:
    rules = load_topic_catalog(Path("data/topic_rules.json"))
    topic = rules.rule_for("registration")
    assert topic is not None
    assert rules.classify_intent("2026학년도 수강신청 안내", topic).key == "registration.main"
    assert rules.classify_intent("수강신청 변경 정정 안내", topic).key == "registration.change"
    assert rules.classify_intent("수강꾸러미 신청 안내", topic).key == "registration.course_basket"
    assert rules.classify_intent("조기취업자 출석인정신청", topic).key == "registration.attendance"


def test_enrich_posts_prefers_title_topic_and_assigns_intent() -> None:
    post = make_post(
        title="2026학년도 수강신청 안내",
        content="개설강좌 조회 화면도 함께 안내합니다.",
    )
    enriched = enrich_posts([post], catalog())[0]
    assert enriched.topic_key == "registration"
    assert enriched.intent_key == "registration.main"
```

- [ ] **Step 2: 실패 확인**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_topic_rules.py backend/tests/test_topic_classifier.py backend/tests/test_chunking.py backend/tests/test_vector_store.py -q`

Expected: FAIL because `IntentRule`, `classify_intent`, and `intent_key` do not exist.

- [ ] **Step 3: catalog와 domain 최소 구현**

```python
@dataclass(frozen=True)
class IntentRule:
    key: str
    label: str
    keywords: tuple[str, ...]
    evidence_markers: tuple[str, ...]
    exclusion_markers: tuple[str, ...]
    example: str


@dataclass(frozen=True)
class TopicRule:
    key: str
    label: str
    keywords: tuple[str, ...]
    suggested_questions: tuple[str, ...]
    evidence_markers: tuple[str, ...] = ()
    intents: tuple[IntentRule, ...] = ()


def classify_intent(self, text: str, topic: TopicRule) -> IntentRule:
    matches = _rank_phrase_matches(text, topic.intents)
    return matches[0] if matches else topic.intents[0]
```

`BoardPost`와 `TextChunk`에 하위 호환 기본값을 가진
`intent_key: str | None = None`을 추가한다. `enrich_posts`는 title로 topic을 먼저
분류한 뒤 default일 때만 본문을 포함해 재분류한다. 선택 topic 안에서 title 기반
intent를 지정하므로 실제 indexing 경로에서는 intent key가 항상 채워진다.

- [ ] **Step 4: topic rules에 수강신청 세부 intent 추가**

```json
{
  "key": "registration.main",
  "label": "일반 수강신청 일정과 공지",
  "keywords": ["수강신청", "수강 신청"],
  "evidence_markers": ["수강신청", "수강 신청"],
  "exclusion_markers": ["변경", "정정", "수강꾸러미", "출석인정"],
  "example": "2026학년도 수강신청 일정과 유의사항"
}
```

registration 아래에 `main`, `change`, `course_basket`, `attendance`를 선언하고
다른 topic에는 명시적인 기본 intent 하나를 선언한다.

- [ ] **Step 5: metadata 저장·조회 테스트 통과**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_topic_rules.py backend/tests/test_topic_classifier.py backend/tests/test_chunking.py backend/tests/test_vector_store.py -q`

Expected: PASS.

- [ ] **Step 6: 커밋**

```bash
git add data/topic_rules.json backend/app/topic_rules.py backend/app/domain.py backend/app/topic_classifier.py backend/app/chunking.py backend/app/vector_store.py backend/tests/test_topic_rules.py backend/tests/test_topic_classifier.py backend/tests/test_chunking.py backend/tests/test_vector_store.py
git commit -m "feat: classify fine-grained notice intents"
```

### Task 2: 자유 질문 Intent 확인 계약

**Files:**
- Create: `backend/app/intent_analysis.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_intent_analysis.py`
- Test: `backend/tests/test_main.py`

- [ ] **Step 1: 후보 생성과 확정 검증 실패 테스트 작성**

```python
def test_registration_question_offers_precise_sibling_intents() -> None:
    analysis = analyze_intents("최근 수강신청 공지를 알려줘", catalog())
    assert [item.intent_key for item in analysis.options] == [
        "registration.main",
        "registration.change",
        "registration.course_basket",
    ]


def test_unknown_or_conflicting_confirmation_is_not_accepted() -> None:
    analysis = analyze_intents("최근 수강신청 공지를 알려줘", catalog())
    assert validate_confirmation(analysis, "career.general") is None


def test_free_text_chat_returns_clarification_without_rag_call(client) -> None:
    response = client.post("/api/chat", json={"question": "최근 수강신청 공지를 알려줘"})
    assert response.status_code == 200
    assert response.json()["response_type"] == "clarification"
    assert response.json()["sources"] == []
```

- [ ] **Step 2: 실패 확인**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_intent_analysis.py backend/tests/test_main.py -q`

Expected: FAIL because clarification models and analyzer do not exist.

- [ ] **Step 3: intent analyzer 구현**

```python
@dataclass(frozen=True)
class IntentOption:
    topic_key: str
    intent_key: str
    label: str
    example: str


@dataclass(frozen=True)
class IntentAnalysis:
    primary: IntentOption
    options: tuple[IntentOption, ...]


def analyze_intents(question: str, catalog: TopicCatalog, limit: int = 3) -> IntentAnalysis:
    topic = catalog.classify(question)
    ranked = rank_intents(question, topic)
    options = tuple(to_option(rule, topic.key) for rule in ranked[:limit])
    return IntentAnalysis(primary=options[0], options=options)


def validate_confirmation(analysis: IntentAnalysis, intent_key: str) -> IntentOption | None:
    return next((item for item in analysis.options if item.intent_key == intent_key), None)
```

general broad department questions에는 `department.overview`, `general.recent` 후보를
제시하고, 단일 제목 단어 중복으로 career를 primary로 만들지 않는다.

- [ ] **Step 4: API Pydantic model 추가**

```python
class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    confirmed_intent_key: str | None = Field(default=None, max_length=100)


class ClarificationOption(BaseModel):
    topic_key: str
    intent_key: str
    label: str
    example: str


class ChatResponse(BaseModel):
    response_type: Literal["clarification", "answer", "no_answer"] = "answer"
    answer: str
    sources: list[AnswerSource]
    grounded: bool
    interpreted_intent: ClarificationOption | None = None
    clarification_options: list[ClarificationOption] = Field(default_factory=list)
```

- [ ] **Step 5: 자유 입력은 clarification, 검증된 intent만 RAG에 전달**

`main.chat`은 먼저 `analyze_intents`를 호출한다. confirmation이 없거나 검증에
실패하면 provider 또는 vector store query를 호출하지 않고 clarification을
반환한다. 검증되면 `service.ask(question, confirmed_intent_key=...)`를 호출한다.

- [ ] **Step 6: 테스트 통과와 커밋**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_intent_analysis.py backend/tests/test_main.py -q`

Expected: PASS.

```bash
git add backend/app/intent_analysis.py backend/app/schemas.py backend/app/main.py backend/tests/test_intent_analysis.py backend/tests/test_main.py
git commit -m "feat: require explicit intent confirmation"
```

### Task 3: Query Planner와 BM25

**Files:**
- Create: `backend/app/query_planner.py`
- Create: `backend/app/lexical_retriever.py`
- Test: `backend/tests/test_query_planner.py`
- Test: `backend/tests/test_lexical_retriever.py`

- [ ] **Step 1: 결정적 rewrite와 BM25 실패 테스트 작성**

```python
def test_query_plan_preserves_original_and_temporal_constraints() -> None:
    plan = build_query_plan(
        "2026학년도 최근 수강신청 공지",
        confirmed_intent("registration.main"),
    )
    assert plan.queries[0] == "2026학년도 최근 수강신청 공지"
    assert any("2026" in query and "수강신청" in query for query in plan.queries)
    assert "수강신청" in plan.hypothetical_notice


def test_bm25_ranks_exact_registration_above_attendance_notice() -> None:
    retriever = BM25Retriever([registration_chunk(), attendance_chunk()])
    results = retriever.search(["최근 수강신청 공지"], top_k=2)
    assert results[0].chunk.intent_key == "registration.main"
```

- [ ] **Step 2: 실패 확인**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_query_planner.py backend/tests/test_lexical_retriever.py -q`

Expected: FAIL because planner and BM25 classes do not exist.

- [ ] **Step 3: QueryPlan 구현**

```python
@dataclass(frozen=True)
class QueryPlan:
    original: str
    queries: tuple[str, ...]
    hypothetical_notice: str


def build_query_plan(question: str, intent: IntentOption, query_intent: QueryIntent) -> QueryPlan:
    temporal = " ".join(part for part in (year_text(query_intent), term_text(query_intent)) if part)
    rewritten = " ".join(part for part in (temporal, intent.label, "공식 공지") if part)
    hyde = f"제목: {rewritten}\n본문: {intent.example}"
    return QueryPlan(question, deduplicate((question, rewritten, hyde)), hyde)
```

- [ ] **Step 4: Okapi BM25 구현**

`BM25Retriever`는 공백 token과 compact 2~4 character n-gram을 사용한다. 문서 빈도,
평균 길이, `k1=1.5`, `b=0.75`를 계산하고 query별 최고 점수를 chunk별로 유지한다.

```python
@dataclass(frozen=True)
class LexicalResult:
    chunk: TextChunk
    score: float
    rank: int


def search(self, queries: Sequence[str], top_k: int) -> list[LexicalResult]:
    scored = [(chunk, max(self._score(chunk, query) for query in queries)) for chunk in self.chunks]
    ordered = sorted(scored, key=lambda item: item[1], reverse=True)
    return [LexicalResult(chunk, score, rank) for rank, (chunk, score) in enumerate(ordered[:top_k], 1) if score > 0]
```

- [ ] **Step 5: 테스트 통과와 커밋**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_query_planner.py backend/tests/test_lexical_retriever.py -q`

Expected: PASS.

```bash
git add backend/app/query_planner.py backend/app/lexical_retriever.py backend/tests/test_query_planner.py backend/tests/test_lexical_retriever.py
git commit -m "feat: add deterministic query planning and BM25"
```

### Task 4: Chroma Corpus 조회와 Hybrid Rank Fusion

**Files:**
- Modify: `backend/app/vector_store.py`
- Create: `backend/app/hybrid_retriever.py`
- Test: `backend/tests/test_vector_store.py`
- Test: `backend/tests/test_hybrid_retriever.py`

- [ ] **Step 1: broad-topic corpus와 RRF 실패 테스트 작성**

```python
def test_list_chunks_filters_topic_without_latest_flag() -> None:
    chunks = store.list_chunks(where={"topic_key": "registration"})
    assert {chunk.intent_key for chunk in chunks} >= {
        "registration.main",
        "registration.attendance",
    }
    assert store.collection.get.call_args.kwargs["where"] == {"topic_key": "registration"}


def test_rrf_preserves_independent_rank_evidence() -> None:
    results = fuse_results(
        lexical=[lexical("main", rank=1)],
        dense=[dense("main", rank=2), dense("attendance", rank=1)],
    )
    main = next(item for item in results if item.chunk.id == "main")
    assert main.lexical_rank == 1
    assert main.dense_rank == 2
    assert main.signal_count == 2
```

- [ ] **Step 2: 실패 확인**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_vector_store.py backend/tests/test_hybrid_retriever.py -q`

Expected: FAIL because `list_chunks` and fusion types do not exist.

- [ ] **Step 3: Chroma get wrapper 구현**

```python
def list_chunks(self, where: dict[str, object] | None = None) -> list[TextChunk]:
    kwargs: dict[str, object] = {"include": ["documents", "metadatas"]}
    if where is not None:
        kwargs["where"] = where
    result = self.collection.get(**kwargs)
    return self._to_chunks(result)
```

query와 get의 metadata 변환을 `_text_chunk` helper로 공유한다.

- [ ] **Step 4: HybridCandidate와 RRF 구현**

```python
@dataclass(frozen=True)
class HybridCandidate:
    chunk: TextChunk
    dense_score: float
    lexical_score: float
    dense_rank: int | None
    lexical_rank: int | None
    fused_score: float

    @property
    def signal_count(self) -> int:
        return int(self.dense_rank is not None) + int(self.lexical_rank is not None)


def reciprocal_rank(rank: int | None, k: int = 60) -> float:
    return 0.0 if rank is None else 1.0 / (k + rank)
```

`HybridRetriever.retrieve`는 broad topic corpus에 BM25를 실행하고, 같은 topic where로
Dense query를 실행한 뒤 chunk id 기준으로 합친다. `is_latest_topic`은 where에 넣지
않는다.

- [ ] **Step 5: 테스트 통과와 커밋**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_vector_store.py backend/tests/test_hybrid_retriever.py -q`

Expected: PASS.

```bash
git add backend/app/vector_store.py backend/app/hybrid_retriever.py backend/tests/test_vector_store.py backend/tests/test_hybrid_retriever.py
git commit -m "feat: fuse lexical and dense retrieval"
```

### Task 5: Reranker, CRAG, Freshness, Compression

**Files:**
- Create: `backend/app/reranker.py`
- Create: `backend/app/relevance_gate.py`
- Create: `backend/app/freshness_selector.py`
- Create: `backend/app/context_compressor.py`
- Test: `backend/tests/test_reranker.py`
- Test: `backend/tests/test_relevance_gate.py`
- Test: `backend/tests/test_freshness_selector.py`
- Test: `backend/tests/test_context_compressor.py`

- [ ] **Step 1: 정확도 정책 실패 테스트 작성**

```python
def test_reranker_rejects_other_registration_subintent_even_when_newer() -> None:
    ranked = rerank(
        [hybrid(attendance_chunk(date="2026-06-16")), hybrid(main_chunk(date="2026-02-11"))],
        confirmed_intent("registration.main"),
        analyze_query_fixture(),
    )
    assert ranked[0].candidate.chunk.intent_key == "registration.main"
    assert ranked[1].has_intent_conflict is True


def test_crag_requires_two_independent_signals_or_exact_title_marker() -> None:
    assert judge_relevance(single_weak_signal()).label == "ambiguous"
    assert judge_relevance(two_agreeing_signals()).label == "relevant"


def test_freshness_runs_after_relevance_and_selects_latest_same_intent() -> None:
    selected = select_freshest([relevant("2026-02-11"), relevant("2025-08-07")])
    assert [item.candidate.chunk.published_at for item in selected] == ["2026-02-11"]


def test_compression_preserves_metadata_and_relevant_sentences() -> None:
    compressed = compress_contexts([retrieved_long_post()], terms=("수강신청", "기간"))
    assert "수강신청 기간" in compressed[0].chunk.text
    assert compressed[0].chunk.url == "https://example.com/main"
```

- [ ] **Step 2: 실패 확인**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_reranker.py backend/tests/test_relevance_gate.py backend/tests/test_freshness_selector.py backend/tests/test_context_compressor.py -q`

Expected: FAIL because policy modules do not exist.

- [ ] **Step 3: RerankedCandidate 구현**

```python
@dataclass(frozen=True)
class RerankedCandidate:
    candidate: HybridCandidate
    score: float
    title_marker_match: bool
    body_marker_match: bool
    temporal_match: bool
    has_intent_conflict: bool


def rerank(candidates, intent, query_intent):
    # Intent conflict is a hard negative. Date is only a tie-breaker.
    return sorted((score_candidate(item, intent, query_intent) for item in candidates), key=rank_key, reverse=True)
```

- [ ] **Step 4: CRAG 판정 구현**

```python
RelevanceLabel = Literal["relevant", "ambiguous", "irrelevant"]


def judge_relevance(item: RerankedCandidate) -> RelevanceDecision:
    if item.has_intent_conflict or not item.temporal_match:
        return RelevanceDecision("irrelevant", "intent_or_time_conflict")
    exact_evidence = item.title_marker_match or item.body_marker_match
    if exact_evidence and item.candidate.signal_count >= 2:
        return RelevanceDecision("relevant", "consensus_with_marker")
    if item.title_marker_match and item.candidate.lexical_rank is not None:
        return RelevanceDecision("relevant", "exact_title_evidence")
    return RelevanceDecision("ambiguous", "insufficient_consensus")
```

- [ ] **Step 5: freshness와 compression 구현**

`select_freshest`는 relevant 후보를 `(intent_key, url)`로 deduplicate하고 같은
intent에서 최신 URL 하나를 선택한다. `compress_contexts`는 query와 intent marker가
많이 겹치는 최대 3문장을 유지한다.

- [ ] **Step 6: 테스트 통과와 커밋**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_reranker.py backend/tests/test_relevance_gate.py backend/tests/test_freshness_selector.py backend/tests/test_context_compressor.py -q`

Expected: PASS.

```bash
git add backend/app/reranker.py backend/app/relevance_gate.py backend/app/freshness_selector.py backend/app/context_compressor.py backend/tests/test_reranker.py backend/tests/test_relevance_gate.py backend/tests/test_freshness_selector.py backend/tests/test_context_compressor.py
git commit -m "feat: gate evidence before freshness selection"
```

### Task 6: RAG Orchestration과 보고된 회귀 수정

**Files:**
- Modify: `backend/app/rag.py`
- Modify: `backend/app/recommendations.py`
- Modify: `backend/app/local_service.py`
- Test: `backend/tests/test_rag.py`
- Test: `backend/tests/test_recommendations.py`
- Test: `backend/tests/test_local_service.py`

- [ ] **Step 1: end-to-end service 실패 테스트 작성**

```python
def test_recent_registration_uses_relevant_notice_before_freshness() -> None:
    service = accuracy_service(
        chunks=[attendance_chunk("2026-06-16"), main_chunk("2026-02-11")]
    )
    result = service.ask(
        "최근 수강신청 공지를 알려줘",
        confirmed_intent_key="registration.main",
    )
    assert result.response_type == "answer"
    assert result.grounded is True
    assert result.sources[0].title == "2026학년도 1학기 수강신청 안내"
    assert all("출석인정" not in source.title for source in result.sources)


def test_department_overview_never_uses_faculty_recruitment() -> None:
    service = accuracy_service(chunks=[faculty_recruitment_chunk()])
    result = service.ask(
        "컴퓨터 소프트웨어 공학과에 대해 알려줘",
        confirmed_intent_key="department.overview",
    )
    assert result.response_type == "no_answer"
    assert result.grounded is False
    assert result.sources == []
```

- [ ] **Step 2: 실패 확인**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_rag.py backend/tests/test_recommendations.py backend/tests/test_local_service.py -q`

Expected: FAIL because the old service filters latest before relevance and has no confirmation parameter.

- [ ] **Step 3: RAGService를 orchestration-only로 교체**

```python
def ask(self, question: str, *, confirmed_intent_key: str) -> ChatResponse:
    analysis = analyze_intents(question, self.topic_catalog)
    confirmed = validate_confirmation(analysis, confirmed_intent_key)
    if confirmed is None:
        return clarification_response(analysis)
    query_intent = analyze_query(question, topic=self.topic_catalog.rule_for(confirmed.topic_key), catalog=self.topic_catalog)
    plan = build_query_plan(question, confirmed, query_intent)
    hybrid = self.hybrid_retriever.retrieve(plan, topic_key=confirmed.topic_key)
    reranked = rerank(hybrid, confirmed, query_intent)
    decisions = evaluate_candidates(reranked)
    relevant = select_freshest(relevant_candidates(decisions))
    if not relevant:
        return no_answer_response(confirmed, decisions)
    contexts = compress_contexts(to_retrieved(relevant), terms=query_intent.match_terms)
    return answer_response(self.provider.answer(question, contexts), contexts, confirmed)
```

기존 사전 latest where filter와 단일 긴 term 승인 경로를 제거한다.

- [ ] **Step 4: 추천과 최근 공지 의미 분리**

`recent_notices`는 confirmed intent와 같은 `intent_key`를 먼저 정렬한다. no-answer
응답에서도 필드는 유지하되 frontend가 참고용 label을 붙일 수 있도록 response type을
사용한다.

- [ ] **Step 5: 테스트 통과와 커밋**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_rag.py backend/tests/test_recommendations.py backend/tests/test_local_service.py -q`

Expected: PASS.

```bash
git add backend/app/rag.py backend/app/recommendations.py backend/app/local_service.py backend/tests/test_rag.py backend/tests/test_recommendations.py backend/tests/test_local_service.py
git commit -m "feat: orchestrate accuracy-first RAG pipeline"
```

### Task 7: 평가 Dataset과 Index 계약 갱신

**Files:**
- Modify: `backend/app/index_manifest.py`
- Modify: `backend/app/evaluation.py`
- Modify: `backend/scripts/evaluate.py`
- Modify: `data/evaluation/questions.json`
- Test: `backend/tests/test_index_manifest.py`
- Test: `backend/tests/test_evaluation.py`
- Test: `backend/tests/test_evaluate_script.py`
- Test: `backend/tests/test_evaluation_dataset.py`

- [ ] **Step 1: intent-aware 평가 실패 테스트 작성**

```python
def test_evaluation_case_requires_confirmed_intent() -> None:
    case = EvaluationCase.model_validate(valid_case())
    assert case.confirmed_intent_key == "registration.main"


def test_evaluation_rejects_source_from_other_subintent() -> None:
    result = evaluate_cases(
        cases=[registration_case()],
        posts=[attendance_post()],
        ask=lambda _q, _intent: attendance_response(),
    )[0]
    assert result.checks.intent_match is False
```

- [ ] **Step 2: 실패 확인**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_index_manifest.py backend/tests/test_evaluation.py backend/tests/test_evaluate_script.py backend/tests/test_evaluation_dataset.py -q`

Expected: FAIL because evaluation cases do not carry confirmed intent.

- [ ] **Step 3: 평가 schema와 dataset 갱신**

`EvaluationCase`에 `confirmed_intent_key`와 `expected_intent_key`를 추가하고 ask callback은
두 인자를 받는다. 필수 회귀 case를 다음처럼 기록한다.

```json
{
  "id": "registration-recent-main",
  "question": "최근 수강신청 공지를 알려줘",
  "confirmed_intent_key": "registration.main",
  "expected_topic_key": "registration",
  "expected_intent_key": "registration.main",
  "expected_latest_only": true,
  "expected_source_title_contains": ["수강신청 안내"]
}
```

department overview no-answer case도 추가한다.

- [ ] **Step 4: index pipeline version 갱신**

intent metadata가 없는 인덱스를 strict compatibility가 거절하도록 index pipeline
version 또는 manifest schema version을 한 단계 올린다.

- [ ] **Step 5: 테스트 통과와 커밋**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_index_manifest.py backend/tests/test_evaluation.py backend/tests/test_evaluate_script.py backend/tests/test_evaluation_dataset.py -q`

Expected: PASS.

```bash
git add backend/app/index_manifest.py backend/app/evaluation.py backend/scripts/evaluate.py data/evaluation/questions.json backend/tests/test_index_manifest.py backend/tests/test_evaluation.py backend/tests/test_evaluate_script.py backend/tests/test_evaluation_dataset.py
git commit -m "test: evaluate confirmed intent precision"
```

### Task 8: Frontend Intent 확인 UI

**Files:**
- Create: `frontend/app/components/IntentClarification.tsx`
- Create: `frontend/app/components/IntentClarification.test.tsx`
- Modify: `frontend/app/components/types.ts`
- Modify: `frontend/app/components/ChatMessage.tsx`
- Modify: `frontend/app/components/RecentNoticeList.tsx`
- Modify: `frontend/app/lib/chatApi.ts`
- Modify: `frontend/app/lib/chatApi.test.ts`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/page.test.tsx`
- Modify: `frontend/app/globals.css`

- [ ] **Step 1: API parsing과 clarification UI 실패 테스트 작성**

```tsx
it("parses a clarification response", async () => {
  const reply = await requestChat("최근 수강신청 공지", {
    apiUrl,
    fetchImpl: mockJson(clarificationPayload),
  });
  expect(reply.response_type).toBe("clarification");
  expect(reply.clarification_options[0].intent_key).toBe("registration.main");
});


it("resends the original question with the selected intent", async () => {
  render(<Home />);
  await ask("최근 수강신청 공지를 알려줘");
  await user.click(screen.getByRole("button", { name: /일반 수강신청 공지/ }));
  expect(fetch).toHaveBeenLastCalledWith(
    expect.stringContaining("/api/chat"),
    expect.objectContaining({ body: JSON.stringify({
      question: "최근 수강신청 공지를 알려줘",
      confirmed_intent_key: "registration.main",
    }) }),
  );
});
```

- [ ] **Step 2: 실패 확인**

Run: `npm --prefix frontend test -- frontend/app/lib/chatApi.test.ts frontend/app/components/IntentClarification.test.tsx frontend/app/page.test.tsx`

Expected: FAIL because response types and clarification component do not exist.

- [ ] **Step 3: TypeScript 계약과 payload 구현**

```typescript
export type ResponseType = "clarification" | "answer" | "no_answer";

export type ClarificationOption = {
  topic_key: string;
  intent_key: string;
  label: string;
  example: string;
};

export async function requestChat(
  question: string,
  { apiUrl, confirmedIntentKey, timeoutMs, fetchImpl }: RequestChatOptions,
): Promise<ChatReply> {
  const body = {
    question,
    ...(confirmedIntentKey ? { confirmed_intent_key: confirmedIntentKey } : {}),
  };
  // Existing timeout and safe error parsing remain unchanged.
}
```

success payload validator는 response type과 clarification option의 모든 문자열을
검증한다. 임의 URL이나 credential-bearing 값은 기존 정책대로 거절한다.

- [ ] **Step 4: IntentClarification과 page 상태 구현**

```tsx
export function IntentClarification({ options, disabled, onSelect }: Props) {
  return (
    <section aria-labelledby="intent-heading" className="intent-panel">
      <h2 id="intent-heading">질문 의도 확인</h2>
      {options.map((option) => (
        <button key={option.intent_key} disabled={disabled} onClick={() => onSelect(option)}>
          <strong>{option.label}</strong>
          <span>{option.example}</span>
        </button>
      ))}
    </section>
  );
}
```

page는 clarification message에 원문 질문을 보존하고 선택 시 사용자 질문 말풍선을
추가하지 않은 채 confirmed request를 보낸다.

- [ ] **Step 5: 최근 공지 의미 label 추가**

`response_type === "no_answer"`이면 “답변 근거와 별개인 참고용 최근 공지”를,
answer이면 “관련 최근 공지”를 표시한다.

- [ ] **Step 6: frontend 테스트 통과와 커밋**

Run: `npm --prefix frontend test`

Expected: all frontend tests PASS.

```bash
git add frontend/app/components/IntentClarification.tsx frontend/app/components/IntentClarification.test.tsx frontend/app/components/types.ts frontend/app/components/ChatMessage.tsx frontend/app/components/RecentNoticeList.tsx frontend/app/lib/chatApi.ts frontend/app/lib/chatApi.test.ts frontend/app/page.tsx frontend/app/page.test.tsx frontend/app/globals.css
git commit -m "feat: add mandatory intent confirmation UI"
```

### Task 9: Reindex와 실제 회귀 검증

**Files:**
- Modify: `backend/tests/test_rag.py`
- Modify: `backend/tests/test_main.py`
- Generated only, do not commit: `chroma_db/`

- [ ] **Step 1: 전체 backend 테스트 실행**

Run: `backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests --cov=backend.app --cov=backend.scripts --cov-config=backend/pyproject.toml --cov-report=term-missing`

Expected: all tests PASS and total coverage at least 85%.

- [ ] **Step 2: lint 실행**

Run: `backend/.venv/Scripts/python.exe -m ruff check backend`

Expected: `All checks passed!`

- [ ] **Step 3: 새 intent metadata로 local index 재생성**

Run: `backend/.venv/Scripts/python.exe -m backend.scripts.index --reset`

Expected: index completes, manifest is compatible, and chunk count is greater than zero.

- [ ] **Step 4: API 프로세스에서 실제 두 단계 회귀 확인**

Run backend and send these requests:

```json
{"question":"최근 수강신청 공지를 알려줘"}
```

Expected: `response_type=clarification`, first option `registration.main`.

```json
{
  "question":"최근 수강신청 공지를 알려줘",
  "confirmed_intent_key":"registration.main"
}
```

Expected: `response_type=answer`, `grounded=true`, no source title contains `출석인정`, and a source title contains `수강신청`.

```json
{
  "question":"컴퓨터 소프트웨어 공학과에 대해 알려줘",
  "confirmed_intent_key":"department.overview"
}
```

Expected: `response_type=no_answer`, `grounded=false`, no faculty recruitment source.

- [ ] **Step 5: frontend 전체 검증**

Run sequentially:

```bash
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend audit --omit=dev
npm --prefix frontend audit
```

Expected: tests, typecheck, lint, and build exit 0; both audits report 0 vulnerabilities.

- [ ] **Step 6: 회귀 보강 커밋**

```bash
git add backend/tests/test_rag.py backend/tests/test_main.py
git commit -m "test: cover accuracy-first RAG regressions"
```

### Task 10: 문서와 최종 상태 기록

**Files:**
- Modify: `README.md`
- Modify: `docs/rag/overview.md`
- Modify: `docs/rag/retrieval-answering.md`
- Modify: `docs/rag/operations-evaluation.md`
- Modify: `docs/PROJECT_STATUS.md`
- Create: `docs/superpowers/handoffs/2026-07-16-accuracy-first-intent-hybrid-rag-handoff.md`

- [ ] **Step 1: 문서에 실제 구현 흐름 반영**

README와 RAG 문서에 다음 순서를 동일하게 기록한다.

```text
free question → clarification → confirmed intent → query plan
→ BM25 + Dense → RRF → rerank → CRAG
→ relevance-scoped freshness → compression → answer + sources
```

사전 `is_latest_topic=true` where filter 설명은 제거하고, offline audit metadata와
online freshness selection 차이를 명시한다.

- [ ] **Step 2: PROJECT_STATUS와 handoff에 검증 수치 기록**

실제로 실행한 backend test count, coverage, frontend test count, build, audit, 실제
API 회귀 결과, Docker 미검증 여부를 기록한다. 추정 수치를 쓰지 않는다.

- [ ] **Step 3: 문서 stale scan과 diff 검사**

Run:

```bash
rg -n "최신 게시글 URL로 범위|is_latest_topic=true.*where|질문을 임베딩한다" README.md docs/rag docs/PROJECT_STATUS.md
git diff --check
```

Expected: stale runtime claims are absent; diff check exits 0.

- [ ] **Step 4: 문서 커밋**

```bash
git add README.md docs/rag/overview.md docs/rag/retrieval-answering.md docs/rag/operations-evaluation.md docs/PROJECT_STATUS.md docs/superpowers/handoffs/2026-07-16-accuracy-first-intent-hybrid-rag-handoff.md
git commit -m "docs: document accuracy-first RAG operations"
```

- [ ] **Step 5: 최종 전체 검증과 clean status**

Run backend full tests with coverage, Ruff, frontend test/typecheck/lint/build, both npm
audits, `git diff --check`, and `git status --short --branch` again from HEAD.

Expected: every command exits 0 and no tracked changes remain.
