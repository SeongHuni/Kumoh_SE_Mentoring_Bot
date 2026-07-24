from __future__ import annotations

from backend.app.domain import BoardPost
from backend.app.freshness import latest_post_keys
from backend.app.topic_rules import IntentRule, TopicCatalog, TopicRule


def _intent_for_key(topic: TopicRule, intent_key: str | None) -> IntentRule | None:
    if intent_key is None:
        return None
    return next(
        (intent for intent in topic.intents if intent.key == intent_key),
        None,
    )


def _fallback_intent(topic: TopicRule) -> IntentRule | None:
    if topic.key == "general":
        return next(
            (intent for intent in topic.intents if intent.key == "general.recent"),
            None,
        )
    if topic.key == "registration":
        return next(
            (intent for intent in topic.intents if intent.key == "registration.main"),
            None,
        )
    return topic.intents[0] if topic.intents else None


def enrich_posts(posts: list[BoardPost], catalog: TopicCatalog) -> list[BoardPost]:
    topicized: list[BoardPost] = []
    for post in posts:
        override = catalog.rule_for(post.topic_key or "")
        title_rule = catalog.classify_title(post.title)
        rule = override or title_rule
        if override is None and title_rule.key == catalog.default_topic_key:
            rule = catalog.classify_body(post.content)
        intent = _intent_for_key(rule, post.intent_key)
        if intent is None and rule.intents:
            intent = catalog.match_intent(post.title, rule)
            if intent is None:
                intent = catalog.match_intent_in_body(post.content, rule)
            if intent is None:
                intent = _fallback_intent(rule)
        topicized.append(
            post.model_copy(
                update={
                    "topic_key": rule.key,
                    "topic_label": rule.label,
                    "category_key": rule.category_key or rule.key,
                    "category_label": rule.category_label or rule.label,
                    "intent_key": intent.key if intent is not None else None,
                    "notice_kind": catalog.classify_notice_kind(
                        post.title,
                        post.content,
                    ),
                }
            )
        )
    latest_keys = latest_post_keys(topicized)
    return [
        post.model_copy(
            update={"is_latest_topic": (post.source, post.id) in latest_keys}
        )
        for post in topicized
    ]
