"""RAG 파이프라인 테스트.

검색 계획기 -> 검색 -> 중요도 가중치 -> 최신 우선 -> 다양성 -> 생성 순서를 검증한다.

이 파일은 topic_catalog / min_score 기반이던 옛 구조를 검증하고 있었다.
그 두 가지를 뺐기 때문에(아래 이유) 새 구조 기준으로 다시 썼다.

  topic_catalog  주제 분류로 검색 범위를 좁히던 것.
                 300문항 측정에서 분류를 완벽히 맞혀도 Recall@5 이득이 6.3pp뿐인데,
                 틀리면 정답이 후보에서 통째로 빠져서 제거했다.
  min_score      점수 컷오프. 근거 부족 판정은 답변 규칙이 하고,
                 순위 조정은 가중치와 다양성이 한다.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from backend.app.domain import RetrievedChunk, TextChunk
from backend.app.rag import RAGService, encode_intent, parse_review_title, to_sources
from backend.app.session import Session


# ------------------------------------------------------------------ 더미
def chunk(
    *,
    post_id: str = "123",
    title: str = "캡스톤디자인 안내",
    text: str = "신청은 통합정보시스템에서 진행합니다.",
    url: str = "https://example.com/123",
    published_at: str = "2026-03-19",
    source: str = "se게시판",
    score: float = 0.9,
) -> RetrievedChunk:
    published_ts = int(published_at.replace("-", "")) if published_at else None
    return RetrievedChunk(
        chunk=TextChunk(
            id=f"{post_id}::D_500::0000",
            post_id=post_id,
            source=source,
            title=title,
            text=text,
            url=url,
            published_at=published_at,
            chunk_index=0,
            topic_key="general",
            topic_label="전체 공지",
            is_latest_topic=True,
        ),
        score=score,
        metadata={
            "original_id": post_id,
            "title": title,
            "source": source,
            "source_url": url,
            "published_at": published_at,
            "published_ts": published_ts,
        },
    )


class FakeProvider:
    """검색 계획기와 답변 생성을 모두 흉내낸다.

    plan 을 바꿔 끼우면 clarify/reject 경로도 시험할 수 있다.
    """

    def __init__(self, plan: dict | None = None) -> None:
        self.plan = plan or {
            "action": "search",
            "standalone_query": "캡스톤디자인 신청 방법",
            "route": None,
            "category_candidates": [],
            "temporal_constraint": {"mode": "none", "year": None, "semester": None},
            "clarifying_question": None,
            "clarification_candidates": [],
        }
        self.embed_calls = 0
        self.answer_calls = 0
        self.contexts: list[RetrievedChunk] = []
        self.last_query: str | None = None

    def chat_json(self, *, system: str, user: str, schema: dict, schema_name: str) -> dict:
        return json.loads(json.dumps(self.plan))

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.embed_calls += 1
        self.last_query = texts[0]
        return [[0.1, 0.2] for _ in texts]

    def answer(self, question: str, contexts: Sequence[RetrievedChunk]) -> str:
        self.answer_calls += 1
        self.contexts = list(contexts)
        return "통합정보시스템에서 신청합니다[1]."


class FakeStore:
    def __init__(self, results: list[RetrievedChunk]) -> None:
        self.results = results
        self.last_where = None
        self.last_top_k = None

    def query(self, embedding, top_k: int, where=None) -> list[RetrievedChunk]:
        self.last_where = where
        self.last_top_k = top_k
        return self.results[:top_k]


def make_service(results: list[RetrievedChunk], provider: FakeProvider | None = None):
    provider = provider or FakeProvider()
    service = RAGService(provider=provider, vector_store=FakeStore(results), top_k=5)
    return service, provider


# ------------------------------------------------------------------ 기본 경로
def test_grounded_answer_returns_sources_in_search_order() -> None:
    service, provider = make_service([chunk()])
    response = service.ask("캡스톤디자인 신청 방법 알려줘")

    assert response.response_type == "answer"
    assert response.grounded is True
    assert provider.answer_calls == 1
    assert response.sources[0].index == 1
    assert response.sources[0].title == "캡스톤디자인 안내"
    assert response.sources[0].url == "https://example.com/123"


def test_search_uses_rewritten_query_not_the_raw_question() -> None:
    """검색은 원문이 아니라 계획기가 다시 쓴 질의로 한다."""
    service, provider = make_service([chunk()])
    service.ask("그거 어떻게 신청해?")

    assert provider.last_query == "캡스톤디자인 신청 방법"


def test_fetches_far_more_than_top_k() -> None:
    """후처리가 손댈 후보가 있어야 한다.

    fetchK 가 30이던 시절, '이정연 장학금'의 정답이 33위라서
    가중치와 다양성 로직이 손댈 대상 자체가 없었다.
    """
    service, _ = make_service([chunk()])
    service.ask("장학금 신청 조건")

    assert service.vector_store.last_top_k >= 100


def test_empty_index_returns_no_answer_without_generation() -> None:
    service, provider = make_service([])
    response = service.ask("아무거나")

    assert response.response_type == "no_answer"
    assert response.grounded is False
    assert provider.answer_calls == 0


# ------------------------------------------------------------------ 되묻기
def test_clarify_does_not_call_search_or_generation() -> None:
    """되묻기는 모델을 호출하지 않는다. 비용과 지연이 0이어야 한다."""
    provider = FakeProvider(
        {
            "action": "clarify",
            "standalone_query": None,
            "route": None,
            "category_candidates": [],
            "temporal_constraint": {"mode": "none", "year": None, "semester": None},
            "clarifying_question": "어떤 장학금에 대해 알고 싶으신가요?",
            "clarification_candidates": [
                {"label": "장학금 종류", "query": "장학금 종류"},
                {"label": "장학금 신청", "query": "장학금 신청 방법"},
            ],
        }
    )
    service, _ = make_service([chunk()], provider)
    response = service.ask("장학금")

    assert response.response_type == "clarification"
    assert [o.label for o in response.clarification_options] == ["장학금 종류", "장학금 신청"]
    assert response.interpreted_intent is not None
    assert provider.embed_calls == 0
    assert provider.answer_calls == 0


def test_clarify_without_candidates_falls_back_to_no_answer() -> None:
    """후보를 못 만들면 되묻기 형식을 만족시킬 수 없으므로 답변 불가로 처리한다."""
    provider = FakeProvider(
        {
            "action": "clarify",
            "standalone_query": None,
            "route": None,
            "category_candidates": [],
            "temporal_constraint": {"mode": "none", "year": None, "semester": None},
            "clarifying_question": "무엇을 찾으시나요?",
            "clarification_candidates": [],
        }
    )
    service, _ = make_service([chunk()], provider)
    response = service.ask("음")

    assert response.response_type == "no_answer"
    assert response.clarification_options == []


def test_confirmed_intent_skips_the_planner() -> None:
    """선택지를 고르면 다시 되묻지 않고 그 질의로 바로 검색한다."""
    provider = FakeProvider({"action": "clarify", "clarification_candidates": []})
    service, _ = make_service([chunk()], provider)

    response = service.ask(
        "장학금", confirmed_intent_key=encode_intent("이정연 장학금 신청 방법")
    )

    assert response.response_type == "answer"
    assert provider.last_query == "이정연 장학금 신청 방법"


def test_reject_returns_out_of_scope_notice() -> None:
    provider = FakeProvider({"action": "reject", "clarification_candidates": []})
    service, _ = make_service([chunk()], provider)
    response = service.ask("오늘 서울 날씨 어때?")

    assert response.response_type == "no_answer"
    assert "범위" in response.answer
    assert provider.answer_calls == 0


# ------------------------------------------------------------------ 후처리
def test_diversify_caps_chunks_from_one_document() -> None:
    """한 공지가 top-k 를 독차지하지 못하게 한다.

    같은 문서에서 최대 2청크까지만 가져온다. 1로 조이면 긴 공지에 답이
    흩어진 질문에서 근거가 잘려 답변이 얕아져서 2로 뒀다.
    """
    crowded = [chunk(post_id="999", score=0.9 - i * 0.01) for i in range(5)]
    # 제목을 서로 다르게 둔다. topic_key 는 숫자를 지우므로
    # "다른 공지 1/2/3" 은 한 주제로 묶여 주제 상한에 먼저 걸린다.
    others = [
        chunk(post_id="o1", title="공결 신청 안내", score=0.80),
        chunk(post_id="o2", title="장학금 신청 안내", score=0.79),
        chunk(post_id="o3", title="현장실습 안내", score=0.78),
    ]
    service, provider = make_service(crowded + others)
    service.ask("캡스톤디자인")

    from_crowded = [c for c in provider.contexts if c.metadata["original_id"] == "999"]
    assert len(from_crowded) == 2
    assert len(provider.contexts) == 5


def test_diversify_refills_when_nothing_else_is_available() -> None:
    """후보가 그 문서뿐이면 상한을 풀어 채운다.

    상한을 그대로 지키면 근거가 2건으로 줄어 답변이 얕아진다.
    '다양성 때문에 결과가 오히려 줄어드는' 상황을 막는 안전장치다.
    """
    same_doc = [chunk(post_id="999", score=0.9 - i * 0.01) for i in range(5)]
    service, provider = make_service(same_doc)
    service.ask("캡스톤디자인")

    assert len(provider.contexts) == 5


def test_latest_wins_among_similar_scores() -> None:
    """관련도가 비슷하면 최신을 앞세운다. 확실히 낮은 것은 건드리지 않는다."""
    provider = FakeProvider(
        {
            "action": "search",
            "standalone_query": "학생회비 납부 안내",
            "route": None,
            "category_candidates": [],
            "temporal_constraint": {"mode": "latest", "year": None, "semester": None},
            "clarifying_question": None,
            "clarification_candidates": [],
        }
    )
    old = chunk(post_id="a", title="2024년 학생회비 납부 안내", published_at="2024-03-02", score=0.90)
    new = chunk(post_id="b", title="2026년 학생회비 납부 안내", published_at="2026-03-19", score=0.88)
    service, provider = make_service([old, new], provider)
    response = service.ask("학생회비는 얼마야?")

    assert response.sources[0].published_at == "2026-03-19"


# ------------------------------------------------------------------ 출처 표기
def test_review_title_is_split_into_course_and_professor() -> None:
    assert parse_review_title("자료구조 (이현아) 강의평 3") == ("자료구조", "이현아")
    assert parse_review_title("[수업] 공결신청 방법 안내") is None


def test_review_sources_have_no_url_but_keep_their_slot() -> None:
    """강의평은 원문 링크가 없다. 그래도 목록에서 빼지 않는다.

    빼면 답변 본문의 [2] 와 화면의 [2] 가 서로 다른 자료를 가리키게 된다.
    """
    review = chunk(
        post_id="et-1",
        title="자료구조 (이현아) 강의평 1",
        source="에브리타임",
        url="",
        published_at="",
    )
    sources = to_sources([chunk(), review])

    assert [s.index for s in sources] == [1, 2]
    assert sources[1].kind == "review"
    assert sources[1].url is None
    assert sources[1].course == "자료구조"
    assert sources[1].professor == "이현아"


def test_session_records_completed_pair() -> None:
    session = Session()
    service, _ = make_service([chunk()])
    service.ask("캡스톤디자인 신청 방법", session)

    assert len(session.pairs) == 1
    assert session.pairs[0].user == "캡스톤디자인 신청 방법"
