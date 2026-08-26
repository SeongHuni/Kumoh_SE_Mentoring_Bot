from datetime import UTC, datetime

from backend.app.domain import BoardPost
from backend.app.recommendations import recent_notices, suggested_questions
from backend.app.topic_rules import TopicCatalog, TopicRule


def catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("course", "개설강좌", ("강좌",), ("강좌 목록을 알려줘",)),
            TopicRule("general", "전체 공지", (), ("최근 공지를 알려줘",)),
        ),
    )


def post(
    post_id: str,
    topic_key: str,
    published_at: str,
    url: str | None = None,
    latest: bool = True,
) -> BoardPost:
    return BoardPost(
        id=post_id,
        source="kumoh",
        title=post_id,
        content="내용",
        url=url or f"https://example.com/{post_id}",
        published_at=published_at,
        crawled_at=datetime.fromisoformat(published_at).replace(tzinfo=UTC),
        topic_key=topic_key,
        topic_label=topic_key,
        is_latest_topic=latest,
    )


def test_suggested_questions_uses_topic_rule_and_limit() -> None:
    assert suggested_questions(catalog(), "course", limit=1) == ["강좌 목록을 알려줘"]


def test_suggested_questions_fills_topic_results_with_general_suggestions() -> None:
    catalog_with_fallback = TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("course", "개설강좌", ("강좌",), ("강좌 목록을 알려줘",)),
            TopicRule(
                "general",
                "전체 공지",
                (),
                ("최근 공지를 알려줘", "학과 공지 요약해줘"),
            ),
        ),
    )

    assert suggested_questions(catalog_with_fallback, "course", limit=3) == [
        "강좌 목록을 알려줘",
        "최근 공지를 알려줘",
        "학과 공지 요약해줘",
    ]


def test_recent_notices_prioritizes_related_latest_posts_and_deduplicates_urls() -> None:
    notices = recent_notices(
        [
            post("other", "general", "2026-03-30"),
            post("course-old", "course", "2026-03-10", url="https://example.com/shared"),
            post("course-new", "course", "2026-03-20", url="https://example.com/shared"),
            post("ignored", "course", "2026-04-01", latest=False),
        ],
        "course",
        catalog(),
    )

    assert [(notice.title, notice.topic_key) for notice in notices] == [
        ("course-new", "course"),
        ("other", "general"),
    ]
