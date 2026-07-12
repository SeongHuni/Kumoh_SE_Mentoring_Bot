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
