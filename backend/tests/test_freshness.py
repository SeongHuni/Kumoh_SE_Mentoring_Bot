from datetime import UTC, datetime

from backend.app.domain import BoardPost
from backend.app.freshness import freshness_key, latest_intent_post, latest_post_keys


def post(post_id: str, published_at: str | None, crawled_at: datetime) -> BoardPost:
    return BoardPost(
        id=post_id,
        source="kumoh",
        title="개설강좌 안내",
        content="내용",
        url=f"https://example.com/{post_id}",
        published_at=published_at,
        crawled_at=crawled_at,
    )


def test_published_at_wins_over_crawled_at() -> None:
    older_crawl = post("old", "2026-03-10", datetime(2026, 7, 1, tzinfo=UTC))
    newer_publish = post("new", "2026-03-20", datetime(2026, 3, 21, tzinfo=UTC))

    assert freshness_key(newer_publish) > freshness_key(older_crawl)


def test_missing_published_at_falls_back_to_crawled_at() -> None:
    first = post("first", None, datetime(2026, 3, 20, tzinfo=UTC))
    second = post("second", None, datetime(2026, 3, 21, tzinfo=UTC))

    assert latest_post_keys([first, second]) == {("kumoh", "second")}


def test_static_documents_do_not_become_latest_notices() -> None:
    notice = post("notice", "2026-03-20", datetime(2026, 3, 21, tzinfo=UTC))
    static = post("static", None, datetime(2026, 7, 24, tzinfo=UTC)).model_copy(
        update={"document_type": "static"}
    )

    assert latest_post_keys([notice, static]) == {("kumoh", "notice")}


def test_historical_documents_do_not_become_latest_notices() -> None:
    notice = post("notice", "2026-03-20", datetime(2026, 3, 21, tzinfo=UTC))
    historical = post("career", None, datetime(2026, 7, 24, tzinfo=UTC)).model_copy(
        update={"document_type": "historical"}
    )

    assert latest_post_keys([notice, historical]) == {("kumoh", "notice")}


def test_historical_documents_do_not_become_latest_intent_posts() -> None:
    historical = post("career", None, datetime(2026, 7, 24, tzinfo=UTC)).model_copy(
        update={"document_type": "historical", "intent_key": "career.general"}
    )
    notice = post("notice", "2026-03-20", datetime(2026, 3, 21, tzinfo=UTC)).model_copy(
        update={"intent_key": "career.general"}
    )

    assert latest_intent_post([historical, notice], "career.general") == notice
