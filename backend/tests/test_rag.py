from collections.abc import Sequence
from datetime import UTC, datetime

from backend.app.domain import BoardPost, RetrievedChunk, TextChunk
from backend.app.rag import NO_ANSWER, RAGService
from backend.app.topic_rules import TopicCatalog, TopicRule


def retrieved(score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=TextChunk(
            id="kumoh:123:0",
            post_id="123",
            source="kumoh",
            title="캡스톤디자인 안내",
            text="신청은 통합정보시스템에서 진행합니다.",
            url="https://example.com/123",
            published_at="2026-03-19",
            chunk_index=0,
            topic_key="general",
            topic_label="전체 공지",
            is_latest_topic=False,
        ),
        score=score,
    )


class FakeProvider:
    answer_called = False

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]

    def answer(self, question: str, contexts: Sequence[RetrievedChunk]) -> str:
        self.answer_called = True
        return "통합정보시스템에서 신청합니다. [자료 1]"


class FakeStore:
    def __init__(self, results: list[RetrievedChunk]) -> None:
        self.results = results
        self.last_where = None

    def query(
        self, embedding: Sequence[float], top_k: int, where=None
    ) -> list[RetrievedChunk]:
        self.last_where = where
        return self.results[:top_k]


def course_catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule(
                "course_openings",
                "개설강좌조회",
                ("개설강좌",),
                ("이번 학기 개설강좌를 알려줘",),
            ),
            TopicRule("general", "전체 공지", (), ("최근 학과 공지를 알려줘",)),
        ),
    )


def retrieved_post(post_id: str, published_at: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=TextChunk(
            id=f"kumoh:{post_id}:0",
            post_id=post_id,
            source="kumoh",
            title="개설강좌 안내",
            text=f"게시글 {post_id} 내용",
            url=f"https://example.com/{post_id}",
            published_at=published_at,
            chunk_index=0,
            topic_key="course_openings",
            topic_label="개설강좌조회",
            is_latest_topic=post_id == "new",
        ),
        score=score,
    )


def retrieved_old() -> RetrievedChunk:
    return retrieved_post("old", "2026-03-10", 0.95)


def retrieved_latest() -> RetrievedChunk:
    return retrieved_post("new", "2026-03-20", 0.9)


def enriched_posts() -> list[BoardPost]:
    return [
        BoardPost(
            id="old",
            source="kumoh",
            title="개설강좌 안내",
            content="이전 내용",
            url="https://example.com/old",
            published_at="2026-03-10",
            crawled_at=datetime(2026, 3, 10, tzinfo=UTC),
            topic_key="course_openings",
            topic_label="개설강좌조회",
            is_latest_topic=False,
        ),
        BoardPost(
            id="new",
            source="kumoh",
            title="개설강좌 안내",
            content="최신 내용",
            url="https://example.com/new",
            published_at="2026-03-20",
            crawled_at=datetime(2026, 3, 20, tzinfo=UTC),
            topic_key="course_openings",
            topic_label="개설강좌조회",
            is_latest_topic=True,
        ),
    ]


def test_rag_returns_grounded_answer_and_source() -> None:
    provider = FakeProvider()
    service = RAGService(provider=provider, vector_store=FakeStore([retrieved()]))  # type: ignore[arg-type]

    result = service.ask("캡스톤디자인은 어디서 신청해?")

    assert result.grounded is True
    assert provider.answer_called is True
    assert result.sources[0].title == "캡스톤디자인 안내"


def test_rag_rejects_low_similarity_without_calling_generation() -> None:
    provider = FakeProvider()
    service = RAGService(
        provider=provider,
        vector_store=FakeStore([retrieved(0.05)]),  # type: ignore[arg-type]
        min_score=0.2,
    )

    result = service.ask("기숙사 식단은 뭐야?")

    assert result.grounded is False
    assert result.answer == NO_ANSWER
    assert provider.answer_called is False


def test_rag_accepts_and_stores_topic_context() -> None:
    provider = FakeProvider()
    catalog = TopicCatalog(default_topic_key="general", rules=())
    posts = [
        BoardPost(
            id="123",
            source="kumoh",
            title="캡스톤디자인 안내",
            content="신청 안내",
            url="https://example.com/123",
        )
    ]

    service = RAGService(
        provider=provider,
        vector_store=FakeStore([]),  # type: ignore[arg-type]
        topic_catalog=catalog,
        posts=posts,
    )

    assert service.topic_catalog is catalog
    assert service.posts == posts


def test_rag_keeps_only_latest_topic_and_returns_followups() -> None:
    provider = FakeProvider()
    store = FakeStore([retrieved_old(), retrieved_latest()])
    service = RAGService(
        provider=provider,
        vector_store=store,  # type: ignore[arg-type]
        topic_catalog=course_catalog(),
        posts=enriched_posts(),
    )

    result = service.ask("개설강좌를 알려줘")

    assert result.grounded is True
    assert result.suggested_questions == [
        "이번 학기 개설강좌를 알려줘",
        "최근 학과 공지를 알려줘",
    ]
    assert result.recent_notices[0].topic_key == "course_openings"
    assert store.last_where == {
        "$and": [
            {"is_latest_topic": True},
            {"topic_key": "course_openings"},
        ]
    }


def test_rag_no_answer_keeps_followups_without_calling_generation() -> None:
    provider = FakeProvider()
    service = RAGService(
        provider=provider,
        vector_store=FakeStore([]),  # type: ignore[arg-type]
        topic_catalog=course_catalog(),
        posts=enriched_posts(),
        min_score=0.2,
    )

    result = service.ask("개설강좌를 알려줘")

    assert result.grounded is False
    assert result.answer == NO_ANSWER
    assert result.suggested_questions == [
        "이번 학기 개설강좌를 알려줘",
        "최근 학과 공지를 알려줘",
    ]
    assert result.recent_notices[0].title == "개설강좌 안내"
    assert provider.answer_called is False
