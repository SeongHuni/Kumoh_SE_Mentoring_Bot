from backend.app.chroma_store import RetrievedDocument
from backend.app.rag import RAGService
from backend.app.schemas import Source


class FakeStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, int | None]] = []

    def search(
        self,
        embedding: list[float],
        *,
        category: str | None = None,
        limit: int | None = None,
    ) -> list[RetrievedDocument]:
        assert embedding == [0.1, 0.2]
        self.calls.append((category, limit))
        if category == "academic":
            return [
                RetrievedDocument(
                    text="academic chunk",
                    source=Source(
                        title="Academic",
                        url="https://example.com/academic",
                        source="notice",
                        published_at=None,
                        score=0.9,
                    ),
                    category="academic",
                )
            ]
        return [
            RetrievedDocument(
                text="first chunk",
                source=Source(
                    title="First",
                    url="https://example.com/first",
                    source="notice",
                    published_at=None,
                    score=0.9,
                ),
                category="academic",
            ),
            RetrievedDocument(
                text="second chunk",
                source=Source(
                    title="Second",
                    url="https://example.com/second",
                    source="notice",
                    published_at=None,
                    score=0.8,
                ),
                category="employment",
            ),
        ]


class FakeClient:
    def embed_query(self, question: str) -> list[float]:
        assert question == "question"
        return [0.1, 0.2]

    def answer(self, question: str, documents: list[RetrievedDocument]) -> str:
        assert [document.source.title for document in documents] == ["Academic"]
        return "grounded answer"


def test_rag_keeps_chroma_order_without_reranking() -> None:
    service = object.__new__(RAGService)
    service.client = FakeClient()
    service.store = FakeStore()
    service.top_k = 5
    service.category_probe_k = 20

    response = service.ask("question")

    assert response.answer == "grounded answer"
    assert [source.title for source in response.sources] == ["Academic"]
    assert service.store.calls == [(None, 20), ("academic", 5)]


def test_professor_evaluation_question_targets_lecture_reviews() -> None:
    assert RAGService._explicit_category("이현아교수님의 평가가 어때?") == "강의평"
