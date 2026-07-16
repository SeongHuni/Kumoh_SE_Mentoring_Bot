from unittest.mock import Mock

import pytest
from backend.app.domain import TextChunk
from backend.app.vector_store import ChromaVectorStore


def make_chunk(
    chunk_id: str,
    title: str,
    intent_key: str | None = None,
) -> TextChunk:
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
        intent_key=intent_key,
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
            intent_key="course_openings.lookup",
            is_latest_topic=True,
        )
    ]

    store.upsert(chunks, [[1.0, 0.0]])

    metadata = store.collection.upsert.call_args.kwargs["metadatas"][0]
    assert metadata["topic_key"] == "course_openings"
    assert metadata["intent_key"] == "course_openings.lookup"
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
                    "intent_key": "course_openings.lookup",
                    "is_latest_topic": True,
                }
            ]
        ],
        "distances": [[0.0]],
    }

    results = store.query(
        [1.0, 0.0],
        top_k=3,
        where={"is_latest_topic": True},
    )

    assert store.collection.query.call_args.kwargs["where"] == {
        "is_latest_topic": True
    }
    assert results[0].chunk.intent_key == "course_openings.lookup"


def test_query_reconstructs_legacy_metadata_without_intent_key() -> None:
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store.collection = Mock()
    store.collection.count.return_value = 1
    store.collection.query.return_value = {
        "ids": [["kumoh:legacy:0"]],
        "documents": [["기존 인덱스"]],
        "metadatas": [
            [
                {
                    "post_id": "legacy",
                    "source": "kumoh",
                    "title": "기존 공지",
                    "url": "https://example.com/legacy",
                    "published_at": "2025-01-01",
                    "chunk_index": 0,
                    "topic_key": "general",
                    "topic_label": "전체 공지",
                    "is_latest_topic": False,
                }
            ]
        ],
        "distances": [[0.0]],
    }

    results = store.query([1.0, 0.0], top_k=1)

    assert results[0].chunk.intent_key is None


def test_list_chunks_forwards_topic_without_implicit_latest_filter() -> None:
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store.collection = Mock()
    store.collection.get.return_value = {
        "ids": ["main", "attendance"],
        "documents": ["수강신청 일정", "출석인정 신청"],
        "metadatas": [
            {
                "post_id": "main-post",
                "source": "kumoh",
                "title": "수강신청",
                "url": "https://example.com/main",
                "published_at": "2026-02-01",
                "chunk_index": 0,
                "topic_key": "registration",
                "topic_label": "수강신청",
                "intent_key": "registration.main",
                "is_latest_topic": False,
            },
            {
                "post_id": "attendance-post",
                "source": "kumoh",
                "title": "출석인정",
                "url": "https://example.com/attendance",
                "published_at": "2026-06-01",
                "chunk_index": 0,
                "topic_key": "registration",
                "topic_label": "수강신청",
                "intent_key": "registration.attendance",
                "is_latest_topic": True,
            },
        ],
    }

    chunks = store.list_chunks(where={"topic_key": "registration"})

    assert {chunk.intent_key for chunk in chunks} == {
        "registration.main",
        "registration.attendance",
    }
    assert store.collection.get.call_args.kwargs["where"] == {
        "topic_key": "registration"
    }


@pytest.mark.parametrize("result", [{}, {"ids": [], "documents": [], "metadatas": []}])
def test_vector_store_handles_empty_or_missing_result_arrays(result: dict) -> None:
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store.collection = Mock()
    store.collection.get.return_value = result
    store.collection.count.return_value = 1
    store.collection.query.return_value = result

    assert store.list_chunks() == []
    assert store.query([1.0, 0.0], top_k=1) == []


def test_vector_store_rejects_mismatched_result_arrays() -> None:
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store.collection = Mock()
    store.collection.get.return_value = {
        "ids": ["one", "two"],
        "documents": ["only one"],
        "metadatas": [{"topic_key": "general", "topic_label": "전체 공지"}, {}],
    }

    with pytest.raises(ValueError, match="mismatched"):
        store.list_chunks()


def test_query_forwards_only_supplied_topic_filter() -> None:
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store.collection = Mock()
    store.collection.count.return_value = 1
    store.collection.query.return_value = {
        "ids": [["one"]],
        "documents": [["본문"]],
        "metadatas": [[
            {
                "post_id": "one",
                "source": "kumoh",
                "title": "공지",
                "url": "https://example.com/one",
                "published_at": "2026-01-01",
                "chunk_index": 0,
                "topic_key": "registration",
                "topic_label": "수강신청",
                "is_latest_topic": False,
            }
        ]],
        "distances": [[0.0]],
    }

    store.query([1.0, 0.0], top_k=1, where={"topic_key": "registration"})

    assert store.collection.query.call_args.kwargs["where"] == {
        "topic_key": "registration"
    }
