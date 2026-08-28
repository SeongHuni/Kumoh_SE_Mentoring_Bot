from types import SimpleNamespace

from backend.app.chroma_store import RetrievedDocument
from backend.app.openai_service import OpenAIRagClient, format_as_bullets
from backend.app.schemas import Source


class FakeResponses:
    def __init__(self) -> None:
        self.request: dict[str, object] | None = None

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.request = kwargs
        return SimpleNamespace(output_text="첫 번째 안내\n둘째 안내")


def document() -> RetrievedDocument:
    return RetrievedDocument(
        text="notice content",
        source=Source(
            title="Notice",
            url="https://example.com/notice",
            source="notice",
            published_at=None,
            score=0.9,
        ),
        category="academic",
    )


def test_answer_requests_bullets_and_normalizes_plain_lines() -> None:
    responses = FakeResponses()
    service = object.__new__(OpenAIRagClient)
    service.answer_client = SimpleNamespace(responses=responses)
    service.settings = SimpleNamespace(answer_model="test-model", answer_temperature=0.0)

    answer = service.answer("question", [document()])

    assert answer == "- 첫 번째 안내\n- 둘째 안내"
    assert responses.request is not None
    assert "개조식" in str(responses.request["instructions"])
    assert responses.request["temperature"] == 0.0


def test_format_as_bullets_preserves_existing_bullets() -> None:
    assert format_as_bullets("- 첫 번째\n- 둘째") == "- 첫 번째\n- 둘째"
