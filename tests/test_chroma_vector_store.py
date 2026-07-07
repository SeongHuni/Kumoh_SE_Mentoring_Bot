from pathlib import Path

from rag_chatbot.document_loader import KnowledgeDocument
from rag_chatbot.document_loader import load_knowledge_documents
from rag_chatbot.vector_store import ChromaKnowledgeIndex, chunk_document


def make_document(
    document_id: str,
    title: str,
    keywords: list[str],
    body: str,
) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=document_id,
        title=title,
        audience="신입생, 재학생",
        source_urls=[f"https://example.com/{document_id}"],
        last_checked="2026-07-07",
        owner="관리자",
        keywords=keywords,
        body=body,
        path=Path(f"{document_id}.md"),
    )


def test_chunk_document_keeps_metadata_and_creates_searchable_text() -> None:
    document = make_document(
        "graduation",
        "졸업 요건",
        ["졸업요건", "졸업학점"],
        "졸업에는 전공 학점과 필수 과목 이수가 필요합니다.\n\n학번별 기준은 다를 수 있습니다.",
    )

    chunks = chunk_document(document, max_chars=40, overlap=10)

    assert len(chunks) >= 2
    assert chunks[0].document.id == "graduation"
    assert chunks[0].chunk_id == "graduation:0"
    assert "졸업 요건" in chunks[0].text


def test_chroma_index_rebuilds_and_searches_relevant_chunks(tmp_path: Path) -> None:
    documents = [
        make_document(
            "graduation",
            "졸업 요건",
            ["졸업요건", "졸업학점"],
            "졸업에는 전공 학점과 필수 과목 이수가 필요합니다.",
        ),
        make_document(
            "events",
            "학과 행사",
            ["오리엔테이션", "행사"],
            "신입생 오리엔테이션과 학과 설명회 일정을 안내합니다.",
        ),
    ]
    index = ChromaKnowledgeIndex(
        documents=documents,
        persist_directory=tmp_path / "chroma",
        collection_name="test_knowledge",
    )

    stats = index.rebuild()
    results = index.search("졸업학점과 필수 과목 알려줘", top_k=2)

    assert stats.document_count == 2
    assert stats.chunk_count >= 2
    assert results[0].document.id == "graduation"
    assert results[0].score > 0


def test_chroma_index_handles_korean_compound_query_against_seed_data(tmp_path: Path) -> None:
    documents = load_knowledge_documents(Path("data/knowledge"))
    index = ChromaKnowledgeIndex(
        documents=documents,
        persist_directory=tmp_path / "chroma",
        collection_name="test_seed_data",
    )

    index.rebuild()
    results = index.search("졸업학점과 필수 과목 알려줘", top_k=4)

    assert results[0].document.id == "graduation_requirements"


def test_chroma_index_accepts_relative_persist_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    documents = [
        make_document(
            "graduation",
            "졸업 요건",
            ["졸업요건", "졸업학점"],
            "졸업에는 전공 학점과 필수 과목 이수가 필요합니다.",
        )
    ]
    index = ChromaKnowledgeIndex(
        documents=documents,
        persist_directory=Path("chroma"),
        collection_name="test_relative_path",
    )

    stats = index.rebuild()
    results = index.search("졸업학점 알려줘", top_k=1)

    assert index.persist_directory.is_absolute()
    assert stats.document_count == 1
    assert results[0].document.id == "graduation"


def test_chroma_client_receives_absolute_persist_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    captured: dict[str, str] = {}

    class DummyClient:
        def __init__(self, path: str):
            captured["path"] = path

    monkeypatch.setattr("rag_chatbot.vector_store.chromadb.PersistentClient", DummyClient)

    ChromaKnowledgeIndex(
        documents=[],
        persist_directory=Path("chroma"),
        collection_name="test_client_path",
    )

    assert Path(captured["path"]).is_absolute()
