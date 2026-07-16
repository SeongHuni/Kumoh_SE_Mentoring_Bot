from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.app.domain import BoardPost, RetrievedChunk, TextChunk
from backend.app.rag import NO_ANSWER, RAGService
from backend.app.topic_rules import TopicCatalog, load_topic_catalog

TOPIC_RULES_PATH = Path(__file__).parents[2] / "data" / "topic_rules.json"


def catalog() -> TopicCatalog:
    return load_topic_catalog(TOPIC_RULES_PATH)


def chunk(
    chunk_id: str,
    *,
    title: str,
    text: str,
    published_at: str,
    topic_key: str,
    intent_key: str,
    latest: bool,
) -> TextChunk:
    return TextChunk(
        id=chunk_id,
        post_id=chunk_id,
        source="kumoh",
        title=title,
        text=text,
        url=f"https://example.com/{chunk_id}",
        published_at=published_at,
        chunk_index=0,
        topic_key=topic_key,
        topic_label=topic_key,
        is_latest_topic=latest,
        intent_key=intent_key,
    )


def registration_main() -> TextChunk:
    return chunk(
        "registration-main",
        title="2026학년도 1학기 수강신청 안내",
        text=(
            "제목: 2026학년도 1학기 수강신청 안내\n"
            "본문: 수강신청 기간은 2월 17일부터입니다. "
            "통합정보시스템에서 신청합니다."
        ),
        published_at="2026-02-11",
        topic_key="registration",
        intent_key="registration.main",
        latest=False,
    )


def attendance_notice() -> TextChunk:
    return chunk(
        "attendance",
        title="2026학년도 여름계절수업 조기취업자 출석인정신청 안내",
        text=(
            "제목: 2026학년도 여름계절수업 조기취업자 출석인정신청 안내\n"
            "본문: 조기취업자는 증빙서류를 제출해 출석인정을 신청합니다."
        ),
        published_at="2026-06-16",
        topic_key="registration",
        intent_key="registration.attendance",
        latest=True,
    )


def faculty_recruitment() -> TextChunk:
    return chunk(
        "faculty",
        title="소프트웨어전공 전임교원 초빙 공개강의 심사 공고",
        text="제목: 전임교원 초빙 공개강의 심사 공고\n본문: 심사 일정과 제출 서류 안내",
        published_at="2026-06-30",
        topic_key="general",
        intent_key="general.recent",
        latest=True,
    )


def capstone_notice() -> TextChunk:
    return chunk(
        "capstone",
        title="2026학년도 1학기 캡스톤디자인 운영 계획 안내",
        text=(
            "제목: 2026학년도 1학기 캡스톤디자인 운영 계획 안내\n"
            "본문: 캡스톤디자인 신청서는 학과 사무실에 제출합니다."
        ),
        published_at="2026-03-19",
        topic_key="capstone",
        intent_key="capstone.general",
        latest=True,
    )


def post_for(item: TextChunk) -> BoardPost:
    return BoardPost(
        id=item.post_id,
        source=item.source,
        title=item.title,
        content=item.text,
        url=item.url,
        published_at=item.published_at,
        crawled_at=datetime(2026, 7, 16, tzinfo=UTC),
        topic_key=item.topic_key,
        topic_label=item.topic_label,
        intent_key=item.intent_key,
        is_latest_topic=item.is_latest_topic,
    )


class FakeProvider:
    def __init__(self) -> None:
        self.embed_calls: list[tuple[str, ...]] = []
        self.answer_calls: list[tuple[str, tuple[RetrievedChunk, ...]]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        values = tuple(texts)
        self.embed_calls.append(values)
        return [[float(index + 1), 0.5] for index, _ in enumerate(values)]

    def answer(self, question: str, contexts: Sequence[RetrievedChunk]) -> str:
        values = tuple(contexts)
        self.answer_calls.append((question, values))
        return "수강신청 기간과 신청 경로를 확인했습니다. [자료 1]"


class FakeStore:
    def __init__(self, chunks: Sequence[TextChunk]) -> None:
        self.chunks = list(chunks)
        self.list_calls: list[dict[str, object] | None] = []
        self.query_calls: list[tuple[tuple[float, ...], int, dict[str, object] | None]] = []

    def _filtered(self, where: dict[str, object] | None) -> list[TextChunk]:
        if not where or "topic_key" not in where:
            return list(self.chunks)
        return [item for item in self.chunks if item.topic_key == where["topic_key"]]

    def list_chunks(self, where: dict[str, object] | None = None) -> list[TextChunk]:
        self.list_calls.append(where)
        return self._filtered(where)

    def query(
        self,
        embedding: Sequence[float],
        top_k: int,
        where: dict[str, object] | None = None,
    ) -> list[RetrievedChunk]:
        self.query_calls.append((tuple(embedding), top_k, where))
        return [
            RetrievedChunk(chunk=item, score=max(0.1, 0.95 - index * 0.1))
            for index, item in enumerate(self._filtered(where)[:top_k])
        ]


def service_for(
    chunks: Sequence[TextChunk],
    *,
    provider: FakeProvider | None = None,
) -> tuple[RAGService, FakeProvider, FakeStore]:
    selected_provider = provider or FakeProvider()
    store = FakeStore(chunks)
    service = RAGService(
        provider=selected_provider,
        vector_store=store,  # type: ignore[arg-type]
        topic_catalog=catalog(),
        posts=[post_for(item) for item in chunks],
        top_k=5,
        min_score=0.2,
    )
    return service, selected_provider, store


def test_recent_registration_uses_relevant_notice_before_freshness() -> None:
    service, provider, store = service_for([attendance_notice(), registration_main()])

    result = service.ask(
        "최근 수강신청 공지를 알려줘",
        confirmed_intent_key="registration.main",
    )

    assert result.response_type == "answer"
    assert result.grounded is True
    assert result.interpreted_intent is not None
    assert result.interpreted_intent.intent_key == "registration.main"
    assert [source.title for source in result.sources] == [
        "2026학년도 1학기 수강신청 안내"
    ]
    assert all("출석인정" not in source.title for source in result.sources)
    assert provider.answer_calls
    assert [item.chunk.id for item in provider.answer_calls[0][1]] == [
        "registration-main"
    ]
    assert store.list_calls == [{"topic_key": "registration"}]
    assert all("is_latest_topic" not in (where or {}) for _, _, where in store.query_calls)


def test_department_overview_never_uses_faculty_recruitment() -> None:
    service, provider, _ = service_for([faculty_recruitment()])

    result = service.ask(
        "컴퓨터 소프트웨어 공학과에 대해 알려줘",
        confirmed_intent_key="department.overview",
    )

    assert result.response_type == "no_answer"
    assert result.answer == NO_ANSWER
    assert result.grounded is False
    assert result.sources == []
    assert result.interpreted_intent is not None
    assert result.interpreted_intent.intent_key == "department.overview"
    assert provider.answer_calls == []


@pytest.mark.parametrize("confirmed_intent_key", [None, "career.general"])
def test_service_fails_closed_before_retrieval_for_unconfirmed_intent(
    confirmed_intent_key: str | None,
) -> None:
    service, provider, store = service_for([registration_main()])

    result = service.ask(
        "최근 수강신청 공지를 알려줘",
        confirmed_intent_key=confirmed_intent_key,
    )

    assert result.response_type == "clarification"
    assert result.grounded is False
    assert result.sources == []
    assert result.clarification_options
    assert result.clarification_options[0].intent_key == "registration.main"
    assert provider.embed_calls == []
    assert provider.answer_calls == []
    assert store.list_calls == []
    assert store.query_calls == []


def test_no_relevant_evidence_returns_no_answer_with_followups() -> None:
    service, provider, _ = service_for([])

    result = service.ask(
        "캡스톤디자인 신청 방법이 뭐야?",
        confirmed_intent_key="capstone.general",
    )

    assert result.response_type == "no_answer"
    assert result.answer == NO_ANSWER
    assert result.grounded is False
    assert result.sources == []
    assert result.suggested_questions
    assert provider.answer_calls == []


def test_grounded_answer_has_sources_interpreted_intent_and_followups() -> None:
    notice = capstone_notice()
    service, provider, _ = service_for([notice])

    result = service.ask(
        "캡스톤디자인 신청 방법이 뭐야?",
        confirmed_intent_key="capstone.general",
    )

    assert result.response_type == "answer"
    assert result.grounded is True
    assert result.sources[0].url == notice.url
    assert result.sources[0].published_at == notice.published_at
    assert result.interpreted_intent is not None
    assert result.interpreted_intent.intent_key == "capstone.general"
    assert result.suggested_questions
    assert result.recent_notices[0].url == notice.url
    assert len(provider.answer_calls) == 1


@pytest.mark.parametrize(
    ("top_k", "min_score"),
    [(0, 0.2), (True, 0.2), (5, -0.1), (5, float("nan"))],
)
def test_service_rejects_invalid_retrieval_configuration(
    top_k: int,
    min_score: float,
) -> None:
    with pytest.raises(ValueError):
        RAGService(
            provider=FakeProvider(),
            vector_store=FakeStore([]),  # type: ignore[arg-type]
            topic_catalog=catalog(),
            top_k=top_k,
            min_score=min_score,
        )
