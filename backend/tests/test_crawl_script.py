from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.app.config import Settings
from backend.app.domain import BoardPost
from backend.app.storage import load_posts, save_posts
from backend.scripts import crawl


def post(post_id: str, source: str) -> BoardPost:
    return BoardPost(
        id=post_id,
        source=source,
        title=f"{source} 공지",
        content="공개 게시글 내용",
        url=f"https://example.com/{source}/{post_id}",
        published_at="2026-07-01",
        crawled_at=datetime(2026, 7, 1, tzinfo=UTC),
    )


def settings(tmp_path: Path) -> Settings:
    return Settings(
        ai_provider="local",
        openai_api_key=None,
        chat_model="local",
        embedding_model="local",
        chroma_path=tmp_path / "chroma",
        chroma_collection="test",
        raw_posts_path=tmp_path / "posts.json",
        topic_rules_path=tmp_path / "topics.json",
        rag_top_k=5,
        rag_min_score=0.09,
        crawler_delay_seconds=0.0,
        crawler_timeout_seconds=1.0,
        seboard_api_url=None,
        seboard_headless=True,
        cors_origins=("http://localhost:3000",),
    )


def test_allow_partial_writes_candidate_without_overwriting_raw_posts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_settings = settings(tmp_path)
    original = post("old", "kumoh")
    save_posts([original], app_settings.raw_posts_path)
    partial_path = tmp_path / "candidates" / "partial.json"

    class GoodKumoh:
        def __init__(self, **_kwargs) -> None:
            pass

        def crawl(self, _limit: int) -> list[BoardPost]:
            return [post("new", "kumoh")]

    class FailedSeBoard:
        def __init__(self, **_kwargs) -> None:
            pass

        def crawl(self, _limit: int) -> list[BoardPost]:
            raise RuntimeError("fixture failure")

    monkeypatch.setattr(crawl, "get_settings", lambda: app_settings)
    monkeypatch.setattr(crawl, "KumohBoardCrawler", GoodKumoh)
    monkeypatch.setattr(crawl, "SeBoardCrawler", FailedSeBoard)

    exit_code = crawl.main(
        [
            "--kumoh-limit",
            "1",
            "--seboard-limit",
            "1",
            "--allow-partial",
            "--partial-output",
            str(partial_path),
        ]
    )

    assert exit_code == 2
    assert [item.id for item in load_posts(app_settings.raw_posts_path)] == ["old"]
    assert [item.id for item in load_posts(partial_path)] == ["new"]


def test_partial_output_cannot_equal_operational_raw_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_settings = settings(tmp_path)
    monkeypatch.setattr(crawl, "get_settings", lambda: app_settings)

    exit_code = crawl.main(
        ["--allow-partial", "--partial-output", str(app_settings.raw_posts_path)]
    )

    assert exit_code == 2
    assert not app_settings.raw_posts_path.exists()
