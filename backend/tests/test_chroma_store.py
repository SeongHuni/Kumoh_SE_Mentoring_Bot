from pathlib import Path

import chromadb
from backend.app.chroma_store import ChromaDataStore
from backend.app.config import Settings


def settings_for(path: Path) -> Settings:
    return Settings(
        embedding_api_key="embedding-key",
        answer_api_key="answer-key",
        embedding_model="text-embedding-3-small",
        answer_model="gpt-4.1-mini",
        chroma_path=path,
        chroma_collection="notices",
        embedding_dimensions=2,
        top_k=2,
    )


def test_inspect_and_search_use_chroma_similarity_order(tmp_path: Path) -> None:
    client = chromadb.PersistentClient(path=str(tmp_path))
    collection = client.create_collection(
        "notices",
        metadata={
            "embedding_model": "text-embedding-3-small",
            "chunk_size_tokens": 500,
            "chunk_overlap_tokens": 0,
            "hnsw:space": "cosine",
        },
    )
    collection.upsert(
        ids=["first", "second"],
        documents=["first notice", "second notice"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadatas=[
            {
                "title": "First",
                "source_url": "https://example.com/first",
                "source": "notice",
                "published_at": "2026-08-01",
                "category": "academic",
            },
            {
                "title": "Second",
                "source_url": "https://example.com/second",
                "source": "notice",
                "published_at": "2026-08-02",
                "category": "employment",
            },
        ],
    )

    store = ChromaDataStore(settings_for(tmp_path))

    assert store.inspect().compatible
    result = store.search([1.0, 0.0])
    assert [item.source.title for item in result] == ["First", "Second"]

    category_result = store.search([1.0, 0.0], category="employment")
    assert [item.source.title for item in category_result] == ["Second"]
