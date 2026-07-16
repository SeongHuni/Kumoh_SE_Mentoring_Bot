from datetime import UTC, datetime
from pathlib import Path

import pytest
from backend.app.domain import BoardPost
from backend.app.topic_classifier import enrich_posts
from backend.app.topic_rules import TopicCatalog, TopicRule, load_topic_catalog


def test_enrich_posts_marks_only_latest_post_per_topic() -> None:
    catalog = TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("course", "수업", ("개설강좌",), ()),
            TopicRule("general", "전체 공지", (), ()),
        ),
    )
    posts = [
        BoardPost(
            id="old",
            source="kumoh",
            title="개설강좌 안내",
            content="이전 내용",
            url="https://example.com/old",
            published_at="2026-03-10",
            crawled_at=datetime(2026, 3, 10, tzinfo=UTC),
        ),
        BoardPost(
            id="new",
            source="kumoh",
            title="개설강좌 안내",
            content="최신 내용",
            url="https://example.com/new",
            published_at="2026-03-20",
            crawled_at=datetime(2026, 3, 20, tzinfo=UTC),
        ),
    ]

    enriched = enrich_posts(posts, catalog)

    assert [(item.id, item.topic_key, item.is_latest_topic) for item in enriched] == [
        ("old", "course", False),
        ("new", "course", True),
    ]
    assert all(item.intent_key is None for item in enriched)


def test_enrich_posts_prefers_title_topic_and_assigns_intent() -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))
    post = BoardPost(
        id="registration",
        source="kumoh",
        title="2026학년도 수강신청 안내",
        content="개설강좌 조회 화면도 함께 안내합니다.",
        url="https://example.com/registration",
    )

    enriched = enrich_posts([post], catalog)[0]

    assert enriched.topic_key == "registration"
    assert enriched.intent_key == "registration.main"


def test_enrich_posts_uses_content_only_when_title_has_default_topic() -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))
    post = BoardPost(
        id="body-fallback",
        source="kumoh",
        title="2026학년도 1학기 안내",
        content="수강신청 기간과 방법을 안내합니다.",
        url="https://example.com/body-fallback",
    )

    enriched = enrich_posts([post], catalog)[0]

    assert enriched.topic_key == "registration"
    assert enriched.intent_key == "registration.main"


@pytest.mark.parametrize(
    ("title", "intent_key"),
    [
        ("2026학년도 수강신청 안내", "registration.main"),
        ("수강신청 변경 정정 안내", "registration.change"),
        ("수강꾸러미 신청 안내", "registration.course_basket"),
        ("조기취업자 출석인정신청", "registration.attendance"),
    ],
)
def test_enrich_posts_assigns_registration_intents_from_title(
    title,
    intent_key,
) -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))
    post = BoardPost(
        id=intent_key,
        source="kumoh",
        title=title,
        content="관련 신청 안내입니다.",
        url=f"https://example.com/{intent_key}",
    )

    enriched = enrich_posts([post], catalog)[0]

    assert enriched.topic_key == "registration"
    assert enriched.intent_key == intent_key


def test_enrich_posts_uses_body_for_intent_when_title_has_no_intent_match() -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))
    post = BoardPost(
        id="body-intent",
        source="kumoh",
        title="학사 행정 안내",
        content="조기취업자 출석인정 신청 방법을 안내합니다.",
        url="https://example.com/body-intent",
    )

    enriched = enrich_posts([post], catalog)[0]

    assert enriched.topic_key == "registration"
    assert enriched.intent_key == "registration.attendance"


def test_enrich_posts_falls_back_to_general_recent_for_unmatched_general_post() -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))
    post = BoardPost(
        id="unrelated-general",
        source="kumoh",
        title="학사 행정 안내",
        content="학생 지원 관련 내용을 확인해 주세요.",
        url="https://example.com/unrelated-general",
    )

    enriched = enrich_posts([post], catalog)[0]

    assert enriched.topic_key == "general"
    assert enriched.intent_key == "general.recent"


def test_enrich_posts_prefers_title_intent_over_conflicting_body() -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))
    post = BoardPost(
        id="title-wins",
        source="kumoh",
        title="수강신청 변경 정정 안내",
        content="수강꾸러미 신청 일정도 함께 안내합니다.",
        url="https://example.com/title-wins",
    )

    enriched = enrich_posts([post], catalog)[0]

    assert enriched.intent_key == "registration.change"


def test_enrich_posts_preserves_explicit_valid_intent_key() -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))
    post = BoardPost(
        id="explicit-intent",
        source="kumoh",
        title="수강신청 안내",
        content="일반 수강신청 일정입니다.",
        url="https://example.com/explicit-intent",
        intent_key="registration.attendance",
    )

    enriched = enrich_posts([post], catalog)[0]

    assert enriched.intent_key == "registration.attendance"
