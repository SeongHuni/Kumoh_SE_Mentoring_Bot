from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TopicRule:
    key: str
    label: str
    keywords: tuple[str, ...]
    suggested_questions: tuple[str, ...]


@dataclass(frozen=True)
class TopicCatalog:
    default_topic_key: str
    rules: tuple[TopicRule, ...]

    def rule_for(self, key: str) -> TopicRule | None:
        return next((rule for rule in self.rules if rule.key == key), None)

    def classify(self, text: str) -> TopicRule:
        normalized = " ".join(text.casefold().split())
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


def load_topic_catalog(path: Path) -> TopicCatalog:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("topics"), list):
        raise ValueError("주제 규칙은 topics 배열을 포함해야 합니다.")
    rules = tuple(
        TopicRule(
            key=str(item["key"]),
            label=str(item["label"]),
            keywords=tuple(str(value) for value in item.get("keywords", [])),
            suggested_questions=tuple(
                str(value) for value in item.get("suggested_questions", [])
            ),
        )
        for item in payload["topics"]
    )
    catalog = TopicCatalog(
        default_topic_key=str(payload.get("default_topic_key", "general")),
        rules=rules,
    )
    if catalog.rule_for(catalog.default_topic_key) is None:
        raise ValueError("default_topic_key에 해당하는 규칙이 없습니다.")
    return catalog
