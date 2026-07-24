from datetime import UTC, datetime

from backend.app.domain import BoardPost
from backend.app.recommendations import recent_notices, suggested_questions
from backend.app.topic_rules import IntentRule, TopicCatalog, TopicRule


def catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("course", "개설강좌", ("강좌",), ("강좌 목록을 알려줘",)),
            TopicRule("general", "전체 공지", (), ("최근 공지를 알려줘",)),
        ),
    )


def post(
    post_id: str,
    topic_key: str,
    published_at: str,
    url: str | None = None,
    latest: bool = True,
    intent_key: str | None = None,
) -> BoardPost:
    return BoardPost(
        id=post_id,
        source="kumoh",
        title=post_id,
        content="내용",
        url=url or f"https://example.com/{post_id}",
        published_at=published_at,
        crawled_at=datetime.fromisoformat(published_at).replace(tzinfo=UTC),
        topic_key=topic_key,
        topic_label=topic_key,
        intent_key=intent_key,
        is_latest_topic=latest,
    )


def test_suggested_questions_uses_topic_rule_and_limit() -> None:
    assert suggested_questions(catalog(), "course", limit=1) == ["강좌 목록을 알려줘"]


def test_suggested_questions_fills_topic_results_with_general_suggestions() -> None:
    catalog_with_fallback = TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("course", "개설강좌", ("강좌",), ("강좌 목록을 알려줘",)),
            TopicRule(
                "general",
                "전체 공지",
                (),
                ("최근 공지를 알려줘", "학과 공지 요약해줘"),
            ),
        ),
    )

    assert suggested_questions(catalog_with_fallback, "course", limit=3) == [
        "강좌 목록을 알려줘",
        "최근 공지를 알려줘",
        "학과 공지 요약해줘",
    ]


def test_recent_notices_prioritizes_related_latest_posts_and_deduplicates_urls() -> None:
    notices = recent_notices(
        [
            post("other", "general", "2026-03-30"),
            post("course-old", "course", "2026-03-10", url="https://example.com/shared"),
            post("course-new", "course", "2026-03-20", url="https://example.com/shared"),
            post("ignored", "course", "2026-04-01", latest=False),
        ],
        "course",
        catalog(),
    )

    assert [(notice.title, notice.topic_key) for notice in notices] == [
        ("course-new", "course"),
        ("other", "general"),
    ]


def test_recent_notices_prioritizes_newest_confirmed_subintent() -> None:
    intent_catalog = TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule(
                "registration",
                "수강신청",
                ("수강신청",),
                ("최근 수강신청 공지를 알려줘",),
                intents=(
                    IntentRule(
                        "registration.main",
                        "일반 수강신청",
                        ("수강신청",),
                        ("수강신청",),
                        ("출석인정",),
                        "수강신청 일정 안내",
                    ),
                    IntentRule(
                        "registration.attendance",
                        "출석인정",
                        ("출석인정",),
                        ("출석인정",),
                        (),
                        "출석인정 안내",
                    ),
                ),
            ),
            TopicRule("general", "전체 공지", (), ("최근 공지를 알려줘",)),
        ),
    )
    notices = recent_notices(
        [
            post(
                "main-old",
                "registration",
                "2026-01-10",
                latest=False,
                intent_key="registration.main",
            ),
            post(
                "main-new",
                "registration",
                "2026-02-10",
                latest=False,
                intent_key="registration.main",
            ),
            post(
                "attendance-newer",
                "registration",
                "2026-06-16",
                latest=True,
                intent_key="registration.attendance",
            ),
            post("general", "general", "2026-07-01"),
        ],
        "registration",
        intent_catalog,
        intent_key="registration.main",
    )

    assert [notice.title for notice in notices] == [
        "main-new",
        "attendance-newer",
        "general",
    ]


def test_recent_notices_deduplicates_confirmed_intent_against_latest_groups() -> None:
    notices = recent_notices(
        [
            post(
                "same",
                "course",
                "2026-03-20",
                url="https://example.com/shared",
                intent_key="course.lookup",
            ),
            post(
                "duplicate",
                "course",
                "2026-03-19",
                url="https://example.com/shared",
                latest=False,
                intent_key="course.lookup",
            ),
        ],
        "course",
        catalog(),
        intent_key="course.lookup",
    )

    assert [notice.url for notice in notices] == ["https://example.com/shared"]


def test_recent_notices_excludes_historical_reference_documents() -> None:
    current = post(
        "current-career-notice",
        "course",
        "2026-07-20",
        intent_key="course.lookup",
    )
    historical = post(
        "historical-career-reference",
        "course",
        "2026-07-24",
        latest=True,
        intent_key="course.lookup",
    ).model_copy(update={"document_type": "historical"})

    notices = recent_notices(
        [historical, current],
        "course",
        catalog(),
        intent_key="course.lookup",
    )

    assert [notice.title for notice in notices] == ["current-career-notice"]
