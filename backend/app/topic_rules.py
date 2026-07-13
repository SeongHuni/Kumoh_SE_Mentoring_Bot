from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RetrievalPolicy:
    recency_terms: tuple[str, ...] = ()
    generic_terms: tuple[str, ...] = ()
    alias_groups: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class TopicRule:
    key: str
    label: str
    keywords: tuple[str, ...]
    suggested_questions: tuple[str, ...]
    evidence_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class TopicCatalog:
    default_topic_key: str
    rules: tuple[TopicRule, ...]
    retrieval_policy: RetrievalPolicy = field(default_factory=RetrievalPolicy)

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


def _clean_strings(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field_name}은 문자열 배열이어야 합니다.")
    cleaned = tuple(str(item).strip() for item in value)
    if any(not item for item in cleaned):
        raise ValueError(f"{field_name}에는 빈 문자열을 둘 수 없습니다.")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field_name}에는 중복 값을 둘 수 없습니다.")
    return cleaned


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


def load_topic_catalog(path: Path) -> TopicCatalog:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("topics"), list):
        raise ValueError("주제 규칙은 topics 배열을 포함해야 합니다.")
    topic_items = payload["topics"]
    keys = [str(item.get("key", "")).strip() for item in topic_items if isinstance(item, dict)]
    if len(keys) != len(topic_items) or any(not key for key in keys):
        raise ValueError("모든 topic은 비어 있지 않은 key를 포함해야 합니다.")
    if len(keys) != len(set(keys)):
        raise ValueError("중복 topic key가 있습니다.")
    rules = tuple(
        TopicRule(
            key=str(item["key"]).strip(),
            label=str(item["label"]).strip(),
            keywords=_clean_strings(item.get("keywords", []), f"{item['key']}.keywords"),
            suggested_questions=_clean_strings(
                item.get("suggested_questions", []),
                f"{item['key']}.suggested_questions",
            ),
            evidence_markers=_clean_strings(
                item.get("evidence_markers", []),
                f"{item['key']}.evidence_markers",
            ),
        )
        for item in topic_items
    )
    catalog = TopicCatalog(
        default_topic_key=str(payload.get("default_topic_key", "general")).strip(),
        rules=rules,
        retrieval_policy=_load_retrieval_policy(payload.get("retrieval_policy")),
    )
    if catalog.rule_for(catalog.default_topic_key) is None:
        raise ValueError("default_topic_key에 해당하는 규칙이 없습니다.")
    return catalog
