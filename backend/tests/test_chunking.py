from backend.app.chunking import chunk_post, normalize_text
from backend.app.domain import BoardPost


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text("첫 줄   내용\n\n\n둘째 줄") == "첫 줄 내용\n둘째 줄"


def test_chunk_post_preserves_source_metadata() -> None:
    post = BoardPost(
        id="42",
        source="kumoh",
        title="수강신청 안내",
        content=("수강신청 기간과 방법을 안내합니다. " * 80),
        published_at="2026-02-11",
        url="https://example.com/posts/42",
    )

    chunks = chunk_post(post, chunk_size=240, overlap=40)

    assert len(chunks) > 1
    assert chunks[0].id == "kumoh:42:0"
    assert all(chunk.post_id == "42" for chunk in chunks)
    assert all(chunk.url == post.url for chunk in chunks)
    assert chunks[0].topic_key == "general"
    assert chunks[0].topic_label == "전체 공지"
    assert chunks[0].intent_key is None
    assert chunks[0].category_key == "other"
    assert chunks[0].category_label == "기타"
    assert chunks[0].notice_kind is None
    assert chunks[0].is_latest_topic is False
    assert chunks[0].text.startswith("제목: 수강신청 안내")


def test_chunk_post_preserves_enriched_topic_metadata() -> None:
    post = BoardPost(
        id="43",
        source="kumoh",
        title="개설강좌 안내",
        content="개설강좌 최신 안내입니다.",
        published_at="2026-02-11",
        url="https://example.com/posts/43",
        topic_key="course",
        topic_label="수업",
        intent_key="course_openings.lookup",
        category_key="course",
        category_label="수업",
        notice_kind="application",
        is_latest_topic=True,
    )

    chunk = chunk_post(post)[0]

    assert chunk.topic_key == "course"
    assert chunk.topic_label == "수업"
    assert chunk.intent_key == "course_openings.lookup"
    assert chunk.category_key == "course"
    assert chunk.category_label == "수업"
    assert chunk.notice_kind == "application"
    assert chunk.is_latest_topic is True


def test_chunk_post_labels_historical_reference_content() -> None:
    post = BoardPost(
        id="career",
        source="kumoh",
        title="졸업 후 진로",
        content="2011년 기준 취업률 정보입니다.",
        url="https://example.com/career",
        document_type="historical",
    )

    chunk = chunk_post(post)[0]

    assert chunk.document_type == "historical"
    assert "문서 상태: 역사 정보" in chunk.text
    assert "현재 수치·현황 아님" in chunk.text
