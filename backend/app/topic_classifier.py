from __future__ import annotations

from backend.app.domain import BoardPost
from backend.app.freshness import latest_post_keys
from backend.app.topic_rules import TopicCatalog


def enrich_posts(posts: list[BoardPost], catalog: TopicCatalog) -> list[BoardPost]:
    topicized: list[BoardPost] = []
    for post in posts:
        override = catalog.rule_for(post.topic_key or "")
        rule = override or catalog.classify(f"{post.title}\n{post.content}")
        topicized.append(
            post.model_copy(
                update={"topic_key": rule.key, "topic_label": rule.label}
            )
        )
    latest_keys = latest_post_keys(topicized)
    return [
        post.model_copy(
            update={"is_latest_topic": (post.source, post.id) in latest_keys}
        )
        for post in topicized
    ]
