from datetime import UTC, datetime

from backend.app.domain import BoardPost
from backend.app.topic_classifier import enrich_posts
from backend.app.topic_rules import TopicCatalog, TopicRule


def test_enrich_posts_marks_only_latest_post_per_topic() -> None:
    catalog = TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("course", "수업", ("개설강좌",), ()),
            TopicRule("general", "전체 공지", (), ()),
        ),
    )
    posts = [
        BoardPost(
            id="old",
            source="kumoh",
            title="개설강좌 안내",
            content="이전 내용",
            url="https://example.com/old",
            published_at="2026-03-10",
            crawled_at=datetime(2026, 3, 10, tzinfo=UTC),
        ),
        BoardPost(
            id="new",
            source="kumoh",
            title="개설강좌 안내",
            content="최신 내용",
            url="https://example.com/new",
            published_at="2026-03-20",
            crawled_at=datetime(2026, 3, 20, tzinfo=UTC),
        ),
    ]

    enriched = enrich_posts(posts, catalog)

    assert [(item.id, item.topic_key, item.is_latest_topic) for item in enriched] == [
        ("old", "course", False),
        ("new", "course", True),
    ]
