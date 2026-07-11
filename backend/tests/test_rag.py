from collections.abc import Sequence

from backend.app.domain import RetrievedChunk, TextChunk
from backend.app.rag import NO_ANSWER, RAGService


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

    def query(self, embedding: Sequence[float], top_k: int) -> list[RetrievedChunk]:
        return self.results[:top_k]


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
