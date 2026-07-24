from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

BODY_CONTEXT_BOUNDARY = re.compile(r"(?:\n+|(?<=[.!?])\s+)")


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _body_contexts(value: str) -> tuple[str, ...]:
    return tuple(part for part in BODY_CONTEXT_BOUNDARY.split(value) if part.strip())


@dataclass(frozen=True)
class RetrievalPolicy:
    recency_terms: tuple[str, ...] = ()
    generic_terms: tuple[str, ...] = ()
    alias_groups: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class IntentRule:
    key: str
    label: str
    keywords: tuple[str, ...]
    evidence_markers: tuple[str, ...]
    exclusion_markers: tuple[str, ...]
    example: str


@dataclass(frozen=True)
class TopicRule:
    key: str
    label: str
    keywords: tuple[str, ...]
    suggested_questions: tuple[str, ...]
    evidence_markers: tuple[str, ...] = ()
    intents: tuple[IntentRule, ...] = ()
    category_key: str = ""
    category_label: str = ""
    title_markers: tuple[str, ...] = ()
    body_action_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class NoticeKindRule:
    key: str
    label: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class TopicCatalog:
    default_topic_key: str
    rules: tuple[TopicRule, ...]
    retrieval_policy: RetrievalPolicy = field(default_factory=RetrievalPolicy)
    notice_kind_rules: tuple[NoticeKindRule, ...] = ()
    default_notice_kind_key: str | None = None

    def rule_for(self, key: str) -> TopicRule | None:
        return next((rule for rule in self.rules if rule.key == key), None)

    def notice_kind_for(self, key: str) -> NoticeKindRule | None:
        return next((rule for rule in self.notice_kind_rules if rule.key == key), None)

    def classify(self, text: str) -> TopicRule:
        normalized = _normalize(text)
        matches: list[tuple[int, int, TopicRule]] = []
        for order, rule in enumerate(self.rules):
            for keyword in rule.keywords:
                normalized_keyword = " ".join(keyword.casefold().split())
                if normalized_keyword and normalized_keyword in normalized:
                    matches.append((len(normalized_keyword), -order, rule))
        if matches:
            return max(matches, key=lambda item: (item[0], item[1]))[2]
        default = self.rule_for(self.default_topic_key)
        if default is None:
            raise ValueError("default_topic_key에 해당하는 규칙이 없습니다.")
        return default

    def classify_title(self, title: str) -> TopicRule:
        """Use semantic title keywords first, then the board's explicit title label."""

        rule = self.classify(title)
        if rule.key != self.default_topic_key:
            return rule
        normalized = _normalize(title)
        matches: list[tuple[int, int, TopicRule]] = []
        for order, candidate in enumerate(self.rules):
            for marker in candidate.title_markers:
                normalized_marker = _normalize(marker)
                if normalized_marker and normalized_marker in normalized:
                    matches.append((len(normalized_marker), -order, candidate))
        if matches:
            return max(matches, key=lambda item: (item[0], item[1]))[2]
        return rule

    def classify_body(self, content: str) -> TopicRule:
        """Classify only when a topic and an action appear in one local context."""

        matches: list[tuple[int, int, int, TopicRule]] = []
        for context in _body_contexts(content):
            normalized = _normalize(context)
            for order, rule in enumerate(self.rules):
                if not rule.body_action_markers:
                    continue
                action_lengths = [
                    len(normalized_marker)
                    for marker in rule.body_action_markers
                    if (normalized_marker := _normalize(marker))
                    and normalized_marker in normalized
                ]
                if not action_lengths:
                    continue
                for keyword in rule.keywords:
                    normalized_keyword = _normalize(keyword)
                    if normalized_keyword and normalized_keyword in normalized:
                        matches.append(
                            (
                                len(normalized_keyword),
                                max(action_lengths),
                                -order,
                                rule,
                            )
                        )
        if matches:
            return max(matches, key=lambda item: (item[0], item[1], item[2]))[3]
        default = self.rule_for(self.default_topic_key)
        if default is None:
            raise ValueError("default_topic_key에 해당하는 규칙이 없습니다.")
        return default

    def match_intent(self, text: str, topic: TopicRule) -> IntentRule | None:
        if not topic.intents:
            raise ValueError(f"{topic.key} topic에 intent 규칙이 없습니다.")
        normalized = _normalize(text)
        matches: list[tuple[int, int, IntentRule]] = []
        for order, intent in enumerate(topic.intents):
            exclusions = (
                " ".join(marker.casefold().split())
                for marker in intent.exclusion_markers
            )
            if any(marker and marker in normalized for marker in exclusions):
                continue
            for keyword in intent.keywords:
                normalized_keyword = " ".join(keyword.casefold().split())
                if normalized_keyword and normalized_keyword in normalized:
                    matches.append((len(normalized_keyword), -order, intent))
        if matches:
            return max(matches, key=lambda item: (item[0], item[1]))[2]
        return None

    def match_intent_in_body(self, content: str, topic: TopicRule) -> IntentRule | None:
        for context in _body_contexts(content):
            match = self.match_intent(context, topic)
            if match is not None:
                return match
        return None

    def classify_intent(self, text: str, topic: TopicRule) -> IntentRule:
        match = self.match_intent(text, topic)
        if match is not None:
            return match
        if not topic.intents:
            raise ValueError(f"{topic.key} topic에 intent 규칙이 없습니다.")
        return topic.intents[0]

    def classify_notice_kind(self, title: str, content: str) -> str | None:
        def match(text: str) -> NoticeKindRule | None:
            normalized = _normalize(text)
            matches: list[tuple[int, int, NoticeKindRule]] = []
            for order, rule in enumerate(self.notice_kind_rules):
                for keyword in rule.keywords:
                    normalized_keyword = _normalize(keyword)
                    if normalized_keyword and normalized_keyword in normalized:
                        matches.append((len(normalized_keyword), -order, rule))
            if not matches:
                return None
            return max(matches, key=lambda item: (item[0], item[1]))[2]

        title_match = match(title)
        if title_match is not None:
            return title_match.key
        for context in _body_contexts(content):
            body_match = match(context)
            if body_match is not None:
                return body_match.key
        return self.default_notice_kind_key


def _clean_strings(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError(f"{field_name}은 문자열 배열이어야 합니다.")
    cleaned = tuple(item.strip() for item in value)
    if any(not item for item in cleaned):
        raise ValueError(f"{field_name}에는 빈 문자열을 둘 수 없습니다.")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field_name}에는 중복 값을 둘 수 없습니다.")
    return cleaned


def _clean_key(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name}는 문자열이어야 합니다.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name}는 비어 있을 수 없습니다.")
    return cleaned


def _load_intents(value: object, topic_key: str) -> tuple[IntentRule, ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{topic_key}.intents는 객체 배열이어야 합니다.")
    if not value:
        raise ValueError(f"{topic_key}에는 명시적인 기본 intent가 필요합니다.")
    intents: list[IntentRule] = []
    for item in value:
        keywords = _clean_strings(
            item.get("keywords", []),
            f"{topic_key}.intent keywords",
        )
        if not keywords:
            raise ValueError(f"{topic_key}.intent keywords에는 하나 이상의 값이 필요합니다.")
        intents.append(
            IntentRule(
                key=_clean_key(item.get("key"), "intent key"),
                label=_clean_key(item.get("label"), f"{topic_key}.intent label"),
                keywords=keywords,
                evidence_markers=_clean_strings(
                    item.get("evidence_markers", []),
                    f"{topic_key}.intent evidence_markers",
                ),
                exclusion_markers=_clean_strings(
                    item.get("exclusion_markers", []),
                    f"{topic_key}.intent exclusion_markers",
                ),
                example=_clean_key(item.get("example"), f"{topic_key}.intent example"),
            )
        )
    return tuple(intents)


def _load_retrieval_policy(value: object) -> RetrievalPolicy:
    if value is None:
        return RetrievalPolicy()
    if not isinstance(value, dict):
        raise ValueError("retrieval_policy는 객체여야 합니다.")
    raw_groups = value.get("alias_groups", [])
    if not isinstance(raw_groups, list):
        raise ValueError("alias_groups는 문자열 배열의 배열이어야 합니다.")
    groups: list[tuple[str, ...]] = []
    for index, group in enumerate(raw_groups):
        cleaned = _clean_strings(group, f"alias group {index}")
        if len(cleaned) < 2:
            raise ValueError("alias group은 서로 다른 표현을 2개 이상 포함해야 합니다.")
        groups.append(cleaned)
    return RetrievalPolicy(
        recency_terms=_clean_strings(value.get("recency_terms", []), "recency_terms"),
        generic_terms=_clean_strings(value.get("generic_terms", []), "generic_terms"),
        alias_groups=tuple(groups),
    )


def _load_notice_kind_rules(value: object) -> tuple[NoticeKindRule, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("notice_kinds는 객체 배열이어야 합니다.")
    rules = tuple(
        NoticeKindRule(
            key=_clean_key(item.get("key"), "notice kind key"),
            label=_clean_key(item.get("label"), "notice kind label"),
            keywords=_clean_strings(
                item.get("keywords", []),
                "notice kind keywords",
            ),
        )
        for item in value
    )
    keys = tuple(rule.key for rule in rules)
    if len(keys) != len(set(keys)):
        raise ValueError("중복 notice kind key가 있습니다.")
    if any(not rule.keywords for rule in rules):
        raise ValueError("notice kind keywords에는 하나 이상의 값이 필요합니다.")
    return rules


def load_topic_catalog(path: Path) -> TopicCatalog:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("topics"), list):
        raise ValueError("주제 규칙은 topics 배열을 포함해야 합니다.")
    topic_items = payload["topics"]
    if any(not isinstance(item, dict) for item in topic_items):
        raise ValueError("모든 topic은 객체여야 합니다.")
    keys = tuple(_clean_key(item.get("key"), "topic key") for item in topic_items)
    if len(keys) != len(set(keys)):
        raise ValueError("중복 topic key가 있습니다.")
    default_topic_key = _clean_key(
        payload.get("default_topic_key", "general"),
        "default_topic_key",
    )
    retrieval_policy = _load_retrieval_policy(payload.get("retrieval_policy"))
    notice_kind_rules = _load_notice_kind_rules(payload.get("notice_kinds"))
    raw_default_notice_kind = payload.get("default_notice_kind_key")
    default_notice_kind_key = (
        None
        if raw_default_notice_kind is None
        else _clean_key(raw_default_notice_kind, "default_notice_kind_key")
    )
    rules = tuple(
        TopicRule(
            key=keys[index],
            label=_clean_key(item.get("label"), f"{keys[index]}.topic label"),
            keywords=_clean_strings(item.get("keywords", []), f"{keys[index]}.keywords"),
            suggested_questions=_clean_strings(
                item.get("suggested_questions", []),
                f"{keys[index]}.suggested_questions",
            ),
            evidence_markers=_clean_strings(
                item.get("evidence_markers", []),
                f"{keys[index]}.evidence_markers",
            ),
            intents=_load_intents(item.get("intents"), keys[index]),
            category_key=_clean_key(
                item.get("category_key", keys[index]),
                f"{keys[index]}.category key",
            ),
            category_label=_clean_key(
                item.get("category_label", item.get("label")),
                f"{keys[index]}.category label",
            ),
            title_markers=_clean_strings(
                item.get("title_markers", []),
                f"{keys[index]}.title_markers",
            ),
            body_action_markers=_clean_strings(
                item.get("body_action_markers", []),
                f"{keys[index]}.body_action_markers",
            ),
        )
        for index, item in enumerate(topic_items)
    )
    intent_keys = tuple(intent.key for rule in rules for intent in rule.intents)
    if len(intent_keys) != len(set(intent_keys)):
        raise ValueError("중복 intent key가 있습니다.")
    catalog = TopicCatalog(
        default_topic_key=default_topic_key,
        rules=rules,
        retrieval_policy=retrieval_policy,
        notice_kind_rules=notice_kind_rules,
        default_notice_kind_key=default_notice_kind_key,
    )
    if catalog.rule_for(catalog.default_topic_key) is None:
        raise ValueError("default_topic_key에 해당하는 규칙이 없습니다.")
    if (
        catalog.default_notice_kind_key is not None
        and catalog.notice_kind_for(catalog.default_notice_kind_key) is None
    ):
        raise ValueError("default_notice_kind_key에 해당하는 규칙이 없습니다.")
    return catalog
