from unittest.mock import Mock

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
        topic_key="general",
        topic_label="전체 공지",
        is_latest_topic=False,
    )


def test_vector_store_returns_nearest_chunk(tmp_path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", "test_posts")
    chunks = [make_chunk("one", "수강신청"), make_chunk("two", "취업특강")]
    store.upsert(chunks, [[1.0, 0.0], [0.0, 1.0]])

    results = store.query([0.95, 0.05], top_k=1)

    assert store.count() == 2
    assert results[0].chunk.title == "수강신청"
    assert results[0].score > 0.9


def test_upsert_stores_topic_metadata() -> None:
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store.collection = Mock()
    chunks = [
        TextChunk(
            id="kumoh:1:0",
            post_id="1",
            source="kumoh",
            title="개설강좌",
            text="최신",
            url="https://example.com/1",
            published_at="2026-03-20",
            chunk_index=0,
            topic_key="course_openings",
            topic_label="개설강좌조회",
            is_latest_topic=True,
        )
    ]

    store.upsert(chunks, [[1.0, 0.0]])

    metadata = store.collection.upsert.call_args.kwargs["metadatas"][0]
    assert metadata["topic_key"] == "course_openings"
    assert metadata["is_latest_topic"] is True


def test_query_forwards_latest_topic_filter() -> None:
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store.collection = Mock()
    store.collection.count.return_value = 1
    store.collection.query.return_value = {
        "ids": [["kumoh:1:0"]],
        "documents": [["최신"]],
        "metadatas": [
            [
                {
                    "post_id": "1",
                    "source": "kumoh",
                    "title": "개설강좌",
                    "url": "https://example.com/1",
                    "published_at": "2026-03-20",
                    "chunk_index": 0,
                    "topic_key": "course_openings",
                    "topic_label": "개설강좌조회",
                    "is_latest_topic": True,
                }
            ]
        ],
        "distances": [[0.0]],
    }

    store.query([1.0, 0.0], top_k=3, where={"is_latest_topic": True})

    assert store.collection.query.call_args.kwargs["where"] == {
        "is_latest_topic": True
    }
