from backend.app.main import app
from backend.app.schemas import ChatResponse, Source
from fastapi.testclient import TestClient


class FakeRagService:
    def ask(self, question: str) -> ChatResponse:
        return ChatResponse(
            answer=f"answer to {question}",
            grounded=True,
            sources=[
                Source(
                    title="Notice",
                    url="https://example.com/notice",
                    source="notice",
                    published_at="2026-08-01",
                    score=0.9,
                )
            ],
        )


def test_live_endpoint_is_available() -> None:
    client = TestClient(app)

    response = client.get("/api/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_chat_uses_frontend_response_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.main.get_settings", lambda: type("S", (), {"api_keys_configured": True})()
    )
    monkeypatch.setattr(
        "backend.app.main.get_store",
        lambda: type("Store", (), {
            "inspect": lambda self: type("Index", (), {"count": 1, "compatible": True})(),
        })(),
    )
    monkeypatch.setattr("backend.app.main.get_rag_service", lambda: FakeRagService())
    client = TestClient(app)

    response = client.post("/api/chat", json={"question": "notice"})

    assert response.status_code == 200
    assert response.json()["answer"] == "answer to notice"
    assert response.json()["sources"][0]["title"] == "Notice"
