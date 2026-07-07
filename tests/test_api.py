from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from starlette.testclient import TestClient

from rag_chatbot.config import Settings
from rag_chatbot.main import create_app


def write_knowledge_file(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "graduation.md").write_text(
        """---
id: graduation
title: 졸업 요건
audience: 재학생
source_urls:
  - https://example.com/graduation
last_checked: 2026-07-07
owner: 관리자
keywords: 졸업요건, 졸업학점
---

## 요약

졸업에는 전공 학점과 필수 과목 이수가 필요합니다.
""",
        encoding="utf-8",
    )


def test_api_rebuilds_index_and_answers_with_chunk_source(tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "knowledge"
    write_knowledge_file(knowledge_dir)
    settings = Settings(
        knowledge_dir=knowledge_dir,
        chroma_dir=tmp_path / "chroma",
        collection_name="test_api",
        top_k=1,
    )
    client = TestClient(create_app(settings))

    index_response = client.post("/index/rebuild")
    chat_response = client.post("/chat", json={"question": "졸업학점 알려줘"})

    assert index_response.status_code == 200
    assert index_response.json()["document_count"] == 1
    assert index_response.json()["chunk_count"] >= 1
    assert chat_response.status_code == 200
    assert chat_response.json()["sources"][0]["id"] == "graduation"
    assert chat_response.json()["sources"][0]["chunk_id"] == "graduation:0"


def test_api_serializes_initial_index_and_chat_requests(tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "knowledge"
    write_knowledge_file(knowledge_dir)
    settings = Settings(
        knowledge_dir=knowledge_dir,
        chroma_dir=tmp_path / "chroma",
        collection_name="test_api_concurrent",
        top_k=1,
    )
    client = TestClient(create_app(settings))

    def rebuild() -> int:
        return client.post("/index/rebuild").status_code

    def chat() -> int:
        return client.post("/chat", json={"question": "졸업학점 알려줘"}).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = [future.result() for future in [executor.submit(rebuild), executor.submit(chat)]]

    assert statuses == [200, 200]
