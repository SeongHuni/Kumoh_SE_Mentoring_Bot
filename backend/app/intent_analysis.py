from __future__ import annotations

from dataclasses import dataclass

from backend.app.topic_rules import IntentRule, TopicCatalog, TopicRule


@dataclass(frozen=True)
class IntentOption:
    topic_key: str
    intent_key: str
    label: str
    example: str


@dataclass(frozen=True)
class IntentAnalysis:
    primary: IntentOption
    options: tuple[IntentOption, ...]


def _to_option(intent: IntentRule, topic_key: str) -> IntentOption:
    return IntentOption(
        topic_key=topic_key,
        intent_key=intent.key,
        label=intent.label,
        example=intent.example,
    )


def _rank_intents(
    topic: TopicRule,
    matched: IntentRule | None,
) -> tuple[IntentRule, ...]:
    if not topic.intents:
        raise ValueError(f"{topic.key} topic에 intent 규칙이 없습니다.")

    if matched is None:
        if topic.key == "general":
            matched = next(
                (intent for intent in topic.intents if intent.key == "general.recent"),
                topic.intents[0],
            )
        else:
            matched = topic.intents[0]

    return (matched,) + tuple(
        intent for intent in topic.intents if intent.key != matched.key
    )


def analyze_intents(
    question: str,
    catalog: TopicCatalog,
    limit: int = 3,
) -> IntentAnalysis:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")

    topic = catalog.classify(question)
    ranked = _rank_intents(topic, catalog.match_intent(question, topic))
    options = tuple(_to_option(intent, topic.key) for intent in ranked[:limit])
    if not options:
        raise ValueError("intent options must not be empty")
    return IntentAnalysis(primary=options[0], options=options)


def validate_confirmation(
    analysis: IntentAnalysis,
    intent_key: str,
) -> IntentOption | None:
    return next(
        (option for option in analysis.options if option.intent_key == intent_key),
        None,
    )
