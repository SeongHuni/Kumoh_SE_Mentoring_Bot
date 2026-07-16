from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from backend.app.domain import BoardPost, RetrievedChunk, TextChunk
from backend.app.rag import NO_ANSWER, RAGService
from backend.app.topic_rules import RetrievalPolicy, TopicCatalog, TopicRule


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


def hardening_catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        retrieval_policy=RetrievalPolicy(
            recency_terms=("최근", "최신"),
            generic_terms=("공지", "알려줘", "찾아줘", "언제"),
            alias_groups=(
                ("개설강좌", "개설 과목", "수강 가능 과목", "수강신청 안내"),
                ("채용", "초빙"),
            ),
        ),
        rules=(
            TopicRule(
                "course_openings",
                "개설",
                ("개설강좌", "개설 과목"),
                (),
                ("수강신청 안내",),
            ),
            TopicRule(
                "registration",
                "수강",
                ("수강신청", "수강 신청", "수강변경"),
                (),
                ("수강신청", "수강변경"),
            ),
            TopicRule(
                "capstone",
                "캡스톤",
                ("캡스톤디자인", "캡스톤 디자인"),
                (),
                ("캡스톤디자인", "캡스톤 디자인"),
            ),
            TopicRule(
                "career",
                "진로",
                ("취업", "채용", "인턴", "진로"),
                (),
                ("취업", "채용", "초빙", "인턴", "진로"),
            ),
            TopicRule(
                "scholarship",
                "장학",
                ("장학금", "장학생", "장학"),
                (),
                ("장학금", "장학생", "장학"),
            ),
            TopicRule("general", "전체", (), ()),
        ),
    )


def policy_result(
    *,
    title: str,
    topic_key: str,
    published_at: str,
    score: float,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=TextChunk(
            id="kumoh:policy:0",
            post_id="policy",
            source="kumoh",
            title=title,
            text=f"제목: {title}\n본문: 테스트 내용",
            url="https://example.com/policy",
            published_at=published_at,
            chunk_index=0,
            topic_key=topic_key,
            topic_label=topic_key,
            is_latest_topic=True,
        ),
        score=score,
    )


def policy_post(title: str, topic_key: str, published_at: str) -> BoardPost:
    return BoardPost(
        id="policy",
        source="kumoh",
        title=title,
        content="테스트 내용",
        url="https://example.com/policy",
        published_at=published_at,
        crawled_at=datetime(2026, 7, 1, tzinfo=UTC),
        topic_key=topic_key,
        topic_label=topic_key,
        is_latest_topic=True,
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

    result = service.ask(
        "캡스톤디자인은 어디서 신청해?",
        confirmed_intent_key="capstone.general",
    )

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


@pytest.mark.parametrize(
    ("question", "topic_key", "title", "published_at"),
    [
        (
            "수강 신청 기간은 언제야?",
            "registration",
            "[수업] 2026학년도 여름계절수업 조기취업자 출석인정신청 안내",
            "2026-06-16",
        ),
        (
            "2026학년도 2학기 캡스톤디자인 공지를 알려줘",
            "capstone",
            "2026학년도 1학기 캡스톤 디자인 운영 계획 안내",
            "2026-03-19",
        ),
        (
            "장학금 신청 공지를 알려줘",
            "scholarship",
            "방산AI인재양성부트캠프사업단 소개 및 설명회 안내",
            "2026-06-17",
        ),
    ],
)
def test_rag_rejects_latest_document_that_does_not_answer_question(
    question: str,
    topic_key: str,
    title: str,
    published_at: str,
) -> None:
    provider = FakeProvider()
    store = FakeStore(
        [
            policy_result(
                title=title,
                topic_key=topic_key,
                published_at=published_at,
                score=0.8,
            )
        ]
    )
    service = RAGService(
        provider=provider,
        vector_store=store,  # type: ignore[arg-type]
        topic_catalog=hardening_catalog(),
        posts=[policy_post(title, topic_key, published_at)],
        min_score=0.09,
    )

    result = service.ask(question)

    assert result.grounded is False
    assert result.sources == []
    assert provider.answer_called is False


def test_rag_uses_alias_to_recover_latest_recruitment_notice() -> None:
    title = "2026년 하반기 소프트웨어전공 전임교원 초빙 공개강의 심사 공고"
    provider = FakeProvider()
    store = FakeStore(
        [
            policy_result(
                title=title,
                topic_key="career",
                published_at="2026-06-30",
                score=0.0,
            )
        ]
    )
    service = RAGService(
        provider=provider,
        vector_store=store,  # type: ignore[arg-type]
        topic_catalog=hardening_catalog(),
        posts=[policy_post(title, "career", "2026-06-30")],
        min_score=0.09,
    )

    result = service.ask("최근 채용 공지를 찾아줘")

    assert result.grounded is True
    assert result.sources[0].title == title


def test_rag_prefers_date_for_general_latest_notice_even_with_zero_score() -> None:
    title = "2026년 하반기 소프트웨어전공 전임교원 초빙 공개강의 심사 공고"
    provider = FakeProvider()
    store = FakeStore(
        [
            policy_result(
                title=title,
                topic_key="career",
                published_at="2026-06-30",
                score=0.0,
            )
        ]
    )
    service = RAGService(
        provider=provider,
        vector_store=store,  # type: ignore[arg-type]
        topic_catalog=hardening_catalog(),
        posts=[policy_post(title, "career", "2026-06-30")],
        min_score=0.09,
    )

    result = service.ask("최근 학과 공지를 알려줘")

    assert result.grounded is True
    assert result.sources[0].published_at == "2026-06-30"
    assert store.last_where == {
        "$and": [
            {"is_latest_topic": True},
            {"url": "https://example.com/policy"},
        ]
    }

def retrieved_semester(semester: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=TextChunk(
            id=f"kumoh:capstone-{semester}:0",
            post_id=f"capstone-{semester}",
            source="kumoh",
            title=f"2026학년도 {semester}학기 캡스톤 디자인 운영 계획 안내",
            text="신청은 학과 사무실에서 접수합니다.",
            url=f"https://example.com/capstone-{semester}",
            published_at="2026-03-19",
            chunk_index=0,
            topic_key="capstone",
            topic_label="캡스톤디자인",
            is_latest_topic=True,
        ),
        score=score,
    )


def test_rag_rejects_conflicting_semester_even_with_high_lexical_score() -> None:
    provider = FakeProvider()
    catalog = TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("capstone", "캡스톤디자인", ("캡스톤디자인", "캡스톤 디자인"), ()),
            TopicRule("general", "전체 공지", (), ()),
        ),
    )
    service = RAGService(
        provider=provider,
        vector_store=FakeStore([retrieved_semester("1", score=0.6)]),  # type: ignore[arg-type]
        topic_catalog=catalog,
        min_score=0.1,
    )

    result = service.ask("2026학년도 2학기 캡스톤디자인 공지를 알려줘")

    assert result.grounded is False
    assert result.answer == NO_ANSWER
    assert provider.answer_called is False


def retrieved_faculty(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=TextChunk(
            id="kumoh:faculty:0",
            post_id="faculty",
            source="kumoh",
            title="전임교원 초빙 공개강의 심사 공고",
            text="심사 절차와 제출 서류 안내",
            url="https://example.com/faculty",
            published_at="2026-06-30",
            chunk_index=0,
            topic_key="career",
            topic_label="진로·취업",
            is_latest_topic=True,
        ),
        score=score,
    )


def test_rag_grounds_synonym_query_via_title_boost() -> None:
    provider = FakeProvider()
    catalog = TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("career", "진로·취업", ("채용",), ()),
            TopicRule("general", "전체 공지", (), ()),
        ),
    )
    service = RAGService(
        provider=provider,
        vector_store=FakeStore([retrieved_faculty(score=0.03)]),  # type: ignore[arg-type]
        topic_catalog=catalog,
        min_score=0.1,
    )

    result = service.ask("최근 채용 공지를 찾아줘")

    assert result.grounded is True
    assert result.sources[0].title == "전임교원 초빙 공개강의 심사 공고"


def test_rag_falls_back_to_newest_for_generic_default_topic_query() -> None:
    provider = FakeProvider()
    catalog = TopicCatalog(
        default_topic_key="general",
        rules=(TopicRule("general", "전체 공지", (), ()),),
    )
    weak_old = retrieved_post("old", "2026-03-10", score=0.02)
    weak_new = retrieved_post("new", "2026-06-01", score=0.01)
    service = RAGService(
        provider=provider,
        vector_store=FakeStore([weak_old, weak_new]),  # type: ignore[arg-type]
        topic_catalog=catalog,
        min_score=0.2,
    )

    result = service.ask("최근 학과 공지를 알려줘")

    assert result.grounded is True
    assert result.sources[0].url == "https://example.com/new"
