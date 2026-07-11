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
    assert chunks[0].text.startswith("제목: 수강신청 안내")
