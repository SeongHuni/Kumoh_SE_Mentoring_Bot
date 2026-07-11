from __future__ import annotations

from backend.app.domain import BoardPost, RecentNotice
from backend.app.freshness import freshness_key
from backend.app.topic_rules import TopicCatalog


def suggested_questions(
    catalog: TopicCatalog, topic_key: str, limit: int = 3
) -> list[str]:
    if limit <= 0:
        return []
    topic_rule = catalog.rule_for(topic_key)
    general_rule = catalog.rule_for(catalog.default_topic_key)
    result: list[str] = []
    for question in (
        topic_rule.suggested_questions if topic_rule else ()
    ) + (general_rule.suggested_questions if general_rule else ()):
        if question in result:
            continue
        result.append(question)
        if len(result) == limit:
            break
    return result


def recent_notices(
    posts: list[BoardPost], topic_key: str, catalog: TopicCatalog, limit: int = 3
) -> list[RecentNotice]:
    latest = [post for post in posts if post.is_latest_topic]
    related = [post for post in latest if post.topic_key == topic_key]
    others = [post for post in latest if post.topic_key != topic_key]
    ordered = sorted(related, key=freshness_key, reverse=True) + sorted(
        others, key=freshness_key, reverse=True
    )
    result: list[RecentNotice] = []
    seen_urls: set[str] = set()
    for post in ordered:
        if post.url in seen_urls:
            continue
        rule = catalog.rule_for(post.topic_key or catalog.default_topic_key)
        if rule is None:
            continue
        seen_urls.add(post.url)
        result.append(
            RecentNotice(
                title=post.title,
                url=post.url,
                source=post.source,
                published_at=post.published_at,
                topic_key=rule.key,
                topic_label=rule.label,
            )
        )
        if len(result) == limit:
            break
    return result
