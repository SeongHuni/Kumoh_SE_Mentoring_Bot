import json

import pytest
from backend.app.topic_rules import load_topic_catalog


def test_catalog_matches_longest_keyword_and_keeps_rule_order(tmp_path) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(
        json.dumps(
            {
                "default_topic_key": "general",
                "topics": [
                    {
                        "key": "course",
                        "label": "수업",
                        "keywords": ["강좌", "개설강좌"],
                        "suggested_questions": ["개설강좌를 알려줘"],
                    },
                    {
                        "key": "general",
                        "label": "전체 공지",
                        "keywords": [],
                        "suggested_questions": ["최근 공지를 알려줘"],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    catalog = load_topic_catalog(path)

    assert catalog.classify("이번 학기 개설강좌가 궁금해").key == "course"
    assert catalog.classify("무슨 공지가 있어?").key == "general"


def test_catalog_rejects_missing_default_topic(tmp_path) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(
        json.dumps({"default_topic_key": "missing", "topics": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="default_topic_key"):
        load_topic_catalog(path)


def test_catalog_loads_evidence_markers_and_retrieval_policy(tmp_path) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(
        json.dumps(
            {
                "default_topic_key": "general",
                "retrieval_policy": {
                    "recency_terms": ["최근", "최신"],
                    "generic_terms": ["공지", "알려줘"],
                    "alias_groups": [["채용", "초빙"]],
                },
                "topics": [
                    {
                        "key": "career",
                        "label": "진로·취업",
                        "keywords": ["채용"],
                        "evidence_markers": ["초빙"],
                        "suggested_questions": [],
                    },
                    {
                        "key": "general",
                        "label": "전체 공지",
                        "keywords": [],
                        "suggested_questions": [],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    catalog = load_topic_catalog(path)

    assert catalog.rule_for("career").evidence_markers == ("초빙",)
    assert catalog.retrieval_policy.recency_terms == ("최근", "최신")
    assert catalog.retrieval_policy.alias_groups == (("채용", "초빙"),)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "default_topic_key": "general",
                "retrieval_policy": {"alias_groups": [["채용"]]},
                "topics": [
                    {"key": "general", "label": "전체", "keywords": []}
                ],
            },
            "alias group",
        ),
        (
            {
                "default_topic_key": "general",
                "topics": [
                    {"key": "general", "label": "전체", "keywords": []},
                    {"key": "general", "label": "중복", "keywords": []},
                ],
            },
            "중복 topic key",
        ),
    ],
)
def test_catalog_rejects_invalid_policy(tmp_path, payload, message) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_topic_catalog(path)
