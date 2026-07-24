import json
from pathlib import Path

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
                        "intents": [_intent_payload("course.general")],
                    },
                    {
                        "key": "general",
                        "label": "전체 공지",
                        "keywords": [],
                        "suggested_questions": ["최근 공지를 알려줘"],
                        "intents": [_intent_payload("general.recent")],
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
                        "intents": [_intent_payload("career.general")],
                    },
                    {
                        "key": "general",
                        "label": "전체 공지",
                        "keywords": [],
                        "suggested_questions": [],
                        "intents": [_intent_payload("general.recent")],
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


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "default_topic_key": "general",
                "topics": [
                    {"key": "general", "label": "전체", "keywords": None}
                ],
            },
            "general.keywords",
        ),
        (
            {
                "default_topic_key": "general",
                "topics": [
                    {
                        "key": "general",
                        "label": "전체",
                        "keywords": [],
                        "suggested_questions": "최근 공지",
                    }
                ],
            },
            "general.suggested_questions",
        ),
        (
            {
                "default_topic_key": "general",
                "retrieval_policy": {"recency_terms": ["최근", 1]},
                "topics": [
                    {"key": "general", "label": "전체", "keywords": []}
                ],
            },
            "recency_terms",
        ),
        (
            {
                "default_topic_key": "general",
                "retrieval_policy": {"alias_groups": [["채용", 1]]},
                "topics": [
                    {"key": "general", "label": "전체", "keywords": []}
                ],
            },
            "alias group 0",
        ),
    ],
)
def test_catalog_rejects_invalid_string_array_types(
    tmp_path,
    payload,
    message,
) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_topic_catalog(path)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "default_topic_key": "1",
                "topics": [{"key": 1, "label": "전체", "keywords": []}],
            },
            "topic key",
        ),
        (
            {
                "default_topic_key": 1,
                "topics": [{"key": "1", "label": "전체", "keywords": []}],
            },
            "default_topic_key",
        ),
    ],
)
def test_catalog_rejects_non_string_keys(tmp_path, payload, message) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_topic_catalog(path)


def test_catalog_classifies_registration_subintents() -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))
    topic = catalog.rule_for("registration")

    assert topic is not None
    assert [intent.key for intent in topic.intents] == [
        "registration.change",
        "registration.course_basket",
        "registration.attendance",
        "registration.main",
        "registration.guidance",
        "registration.evaluation",
        "registration.grades",
    ]
    assert (
        catalog.classify_intent("2026학년도 수강신청 안내", topic).key
        == "registration.main"
    )
    assert (
        catalog.classify_intent("수강신청 변경 정정 안내", topic).key
        == "registration.change"
    )
    assert (
        catalog.classify_intent("수강꾸러미 신청 안내", topic).key
        == "registration.course_basket"
    )
    assert (
        catalog.classify_intent("조기취업자 출석인정신청", topic).key
        == "registration.attendance"
    )


def test_real_catalog_declares_intents_for_every_topic() -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))

    assert all(rule.intents for rule in catalog.rules)
    general = catalog.rule_for("general")
    assert general is not None
    assert [intent.key for intent in general.intents] == [
        "department.overview",
        "general.recent",
    ]
    assert general.intents[0].keywords == (
        "학과 소개",
        "전공 소개",
        "소프트웨어 공학과",
        "컴퓨터 소프트웨어 공학과",
    )


def test_intent_classification_uses_longest_phrase_rule_order_and_default(
    tmp_path,
) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(
        json.dumps(
            {
                "default_topic_key": "general",
                "topics": [
                    {
                        "key": "general",
                        "label": "전체",
                        "keywords": [],
                        "suggested_questions": [],
                        "intents": [
                            {
                                "key": "general.short",
                                "label": "짧은 표현",
                                "keywords": ["변경", "동일"],
                                "evidence_markers": [],
                                "exclusion_markers": [],
                                "example": "짧은 표현",
                            },
                            {
                                "key": "general.long",
                                "label": "긴 표현",
                                "keywords": ["수강 변경", "동일"],
                                "evidence_markers": [],
                                "exclusion_markers": [],
                                "example": "긴 표현",
                            },
                            {
                                "key": "general.default",
                                "label": "기본",
                                "keywords": ["기본 공지"],
                                "evidence_markers": [],
                                "exclusion_markers": [],
                                "example": "기본 공지",
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    catalog = load_topic_catalog(path)
    topic = catalog.rule_for("general")

    assert topic is not None
    assert catalog.classify_intent("수강   변경 안내", topic).key == "general.long"
    assert catalog.classify_intent("동일 안내", topic).key == "general.short"
    assert catalog.classify_intent("표현 없는 안내", topic).key == "general.short"


def _intent_payload(key: object) -> dict[str, object]:
    return {
        "key": key,
        "label": "의도",
        "keywords": ["표현"],
        "evidence_markers": [],
        "exclusion_markers": [],
        "example": "예시",
    }


@pytest.mark.parametrize(
    ("intents", "message"),
    [
        ([], "기본 intent"),
        ([_intent_payload(" ")], "intent key"),
        (
            [_intent_payload("general.same"), _intent_payload("general.same")],
            "중복 intent key",
        ),
    ],
)
def test_catalog_rejects_invalid_intent_keys_and_missing_default(
    tmp_path,
    intents,
    message,
) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(
        json.dumps(
            {
                "default_topic_key": "general",
                "topics": [
                    {
                        "key": "general",
                        "label": "전체",
                        "keywords": [],
                        "suggested_questions": [],
                        "intents": intents,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_topic_catalog(path)


def test_catalog_rejects_duplicate_intent_keys_across_topics(tmp_path) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(
        json.dumps(
            {
                "default_topic_key": "general",
                "topics": [
                    {
                        "key": topic_key,
                        "label": topic_key,
                        "keywords": [],
                        "suggested_questions": [],
                        "intents": [_intent_payload("shared.intent")],
                    }
                    for topic_key in ("course", "general")
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="중복 intent key"):
        load_topic_catalog(path)


def test_catalog_rejects_topic_without_intents(tmp_path) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(
        json.dumps(
            {
                "default_topic_key": "general",
                "topics": [
                    {
                        "key": "general",
                        "label": "전체",
                        "keywords": [],
                        "suggested_questions": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="intents"):
        load_topic_catalog(path)


def test_catalog_rejects_intent_with_empty_keywords(tmp_path) -> None:
    path = tmp_path / "topic_rules.json"
    payload = _intent_payload("general.recent")
    payload["keywords"] = []
    path.write_text(
        json.dumps(
            {
                "default_topic_key": "general",
                "topics": [
                    {
                        "key": "general",
                        "label": "전체",
                        "keywords": [],
                        "suggested_questions": [],
                        "intents": [payload],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="intent keywords"):
        load_topic_catalog(path)


def test_catalog_rejects_blank_topic_label(tmp_path) -> None:
    path = tmp_path / "topic_rules.json"
    path.write_text(
        json.dumps(
            {
                "default_topic_key": "general",
                "topics": [
                    {
                        "key": "general",
                        "label": " ",
                        "keywords": [],
                        "suggested_questions": [],
                        "intents": [_intent_payload("general.recent")],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="topic label"):
        load_topic_catalog(path)


def test_general_notice_does_not_classify_as_department_overview() -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))
    topic = catalog.rule_for("general")

    assert topic is not None
    assert (
        catalog.classify_intent("소프트웨어 공학과 공지 안내", topic).key
        == "general.recent"
    )
