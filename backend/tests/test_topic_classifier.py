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


@pytest.mark.parametrize(
    ("title", "content", "topic_key", "category_key", "notice_kind"),
    [
        (
            "[수업] 2026학년도 1학기 수강신청 안내",
            "수강신청 기간과 방법을 안내합니다.",
            "registration",
            "course",
            "application",
        ),
        (
            "[학적] 2026학년도 마이크로디그리 이수 신청 안내",
            "취업 연계 프로그램도 함께 소개합니다.",
            "graduation",
            "academic",
            "application",
        ),
        (
            "[장학] 외국어성적우수장학금 신청 안내",
            "제출 서류와 신청 기간을 확인하세요.",
            "scholarship",
            "scholarship",
            "application",
        ),
        (
            "삼성청년SW·AI아카데미 SSAFY 모집 안내",
            "교육 과정 참가자를 모집합니다.",
            "career",
            "career",
            "application",
        ),
        (
            "[교내행사] AX 기반 역량 강화 공모전 안내",
            "참가 신청을 받습니다.",
            "extracurricular",
            "extracurricular",
            "event",
        ),
        (
            "2026학년도 캡스톤 디자인 운영 계획 안내",
            "캡스톤디자인 신청과 일정을 안내합니다.",
            "capstone",
            "research_capstone",
            "guide",
        ),
        (
            "[대학원] 학·석사학위 연계과정 지원자 모집",
            "대학원 지원자 모집 안내입니다.",
            "graduate",
            "graduate",
            "application",
        ),
        (
            "2026학년도 전학년 MT 안내",
            "학생회에서 참가 신청을 받습니다.",
            "student_council",
            "student_council",
            "event",
        ),
        (
            "[수업] 2026학년도 1학기 공결신청 방법 안내",
            "조기취업자는 별도 증빙을 제출합니다.",
            "administration",
            "administration",
            "policy",
        ),
        (
            "금오톡톡 알림 기능 중단 안내",
            "서비스 기능이 중단됩니다.",
            "administration",
            "administration",
            "information",
        ),
    ],
)
def test_enrich_posts_assigns_the_mentoring_taxonomy_from_title_first(
    title: str,
    content: str,
    topic_key: str,
    category_key: str,
    notice_kind: str,
) -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))
    post = BoardPost(
        id=category_key,
        source="kumoh",
        title=title,
        content=content,
        url=f"https://example.com/{category_key}",
    )

    enriched = enrich_posts([post], catalog)[0]

    assert enriched.topic_key == topic_key
    assert enriched.category_key == category_key
    assert enriched.notice_kind == notice_kind


def test_enrich_posts_does_not_promote_an_incidental_body_topic() -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))
    post = BoardPost(
        id="incidental-body-topic",
        source="kumoh",
        title="2026년 안내",
        content="홈커밍데이에서 캡스톤디자인 프로젝트 발표를 소개했습니다.",
        url="https://example.com/incidental-body-topic",
    )

    enriched = enrich_posts([post], catalog)[0]

    assert enriched.topic_key == "general"
    assert enriched.category_key == "other"


def test_enrich_posts_prefers_a_specific_event_over_a_broad_career_center_marker() -> None:
    catalog = load_topic_catalog(Path("data/topic_rules.json"))
    post = BoardPost(
        id="programming-contest",
        source="kumoh",
        title="[대학일자리플러스센터] 프로그래밍 경진대회 신청 안내",
        content="재학생 참가 신청을 받습니다.",
        url="https://example.com/programming-contest",
    )

    enriched = enrich_posts([post], catalog)[0]

    assert enriched.topic_key == "extracurricular"
    assert enriched.category_key == "extracurricular"
