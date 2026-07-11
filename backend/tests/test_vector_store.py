from backend.app.domain import TextChunk
from backend.app.vector_store import ChromaVectorStore


def make_chunk(chunk_id: str, title: str) -> TextChunk:
    return TextChunk(
        id=chunk_id,
        post_id=chunk_id,
        source="kumoh",
        title=title,
        text=f"{title} 본문",
        url=f"https://example.com/{chunk_id}",
        published_at="2026-01-01",
        chunk_index=0,
    )


def test_vector_store_returns_nearest_chunk(tmp_path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", "test_posts")
    chunks = [make_chunk("one", "수강신청"), make_chunk("two", "취업특강")]
    store.upsert(chunks, [[1.0, 0.0], [0.0, 1.0]])

    results = store.query([0.95, 0.05], top_k=1)

    assert store.count() == 2
    assert results[0].chunk.title == "수강신청"
    assert results[0].score > 0.9
