from __future__ import annotations

from datetime import UTC, datetime

from backend.app.domain import BoardPost


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def parse_published_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _aware(parsed)


def freshness_key(post: BoardPost) -> tuple[int, datetime, datetime]:
    crawled_at = _aware(post.crawled_at)
    published_at = parse_published_at(post.published_at)
    if published_at is None:
        return (0, crawled_at, crawled_at)
    return (1, published_at, crawled_at)


def latest_post_keys(posts: list[BoardPost]) -> set[tuple[str, str]]:
    latest: dict[str, BoardPost] = {}
    for post in posts:
        current = latest.get(post.topic_key or "general")
        if current is None or freshness_key(post) > freshness_key(current):
            latest[post.topic_key or "general"] = post
    return {(post.source, post.id) for post in latest.values()}
