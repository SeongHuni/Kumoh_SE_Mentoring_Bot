from datetime import UTC, datetime

import pytest
from backend.app.data_audit import audit_posts, render_markdown
from backend.app.domain import BoardPost
from backend.app.topic_rules import TopicCatalog, TopicRule


def catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("course_openings", "개설", ("개설강좌",), ()),
            TopicRule("graduation", "졸업", ("졸업요건",), ()),
            TopicRule("general", "전체", (), ()),
        ),
    )


def post(
    post_id: str,
    *,
    source: str = "kumoh",
    published_at: str | None = "2025-08-07",
    topic_key: str | None = "course_openings",
) -> BoardPost:
    return BoardPost(
        id=post_id,
        source=source,
        title="2025학년도 2학기 개설강좌 안내",
        content="감사 보고서에 포함되면 안 되는 비공개 테스트 본문",
        url=f"https://example.com/{post_id}",
        published_at=published_at,
        crawled_at=datetime(2025, 8, 8, tzinfo=UTC),
        topic_key=topic_key,
    )


def test_audit_reports_missing_source_staleness_and_empty_topic_without_body() -> None:
    report = audit_posts(
        [post("1")],
        catalog=catalog(),
        required_sources=("kumoh", "seboard"),
        stale_after_days=180,
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
    )

    assert report.total_posts == 1
    assert report.source_counts == {"kumoh": 1}
    assert report.topic_summaries[0].topic_key == "course_openings"
    assert {issue.code for issue in report.issues} >= {
        "missing_source",
        "stale_topic",
        "empty_topic",
    }
    serialized = report.model_dump_json()
    markdown = render_markdown(report)
    assert "비공개 테스트 본문" not in serialized
    assert "비공개 테스트 본문" not in markdown


def test_audit_reports_missing_or_invalid_published_date() -> None:
    report = audit_posts(
        [post("missing", published_at=None), post("invalid", published_at="not-a-date")],
        catalog=catalog(),
        required_sources=("kumoh",),
        stale_after_days=180,
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
    )

    assert [issue.code for issue in report.issues].count("missing_published_at") == 2


def test_audit_allows_undated_static_documents() -> None:
    static = post("static", published_at=None).model_copy(
        update={"document_type": "static"}
    )

    report = audit_posts(
        [static],
        catalog=catalog(),
        required_sources=("kumoh",),
        stale_after_days=180,
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
    )

    assert "missing_published_at" not in [issue.code for issue in report.issues]


def test_audit_allows_undated_historical_documents() -> None:
    historical = post("career", published_at=None).model_copy(
        update={"document_type": "historical"}
    )

    report = audit_posts(
        [historical],
        catalog=catalog(),
        required_sources=("kumoh",),
        stale_after_days=180,
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
    )

    assert "missing_published_at" not in [issue.code for issue in report.issues]


def test_audit_only_checks_explicit_topic_overrides() -> None:
    rules = TopicCatalog(
        default_topic_key="general",
        rules=(
            TopicRule("course", "수업", ("수강",), ()),
            TopicRule("academic", "학적", ("졸업요건",), ()),
            TopicRule("general", "전체", (), ()),
        ),
    )
    inferred = BoardPost(
        id="inferred",
        source="kumoh",
        title="수강 안내",
        content="졸업요건이라는 단어가 본문에 한 번 등장합니다.",
        url="https://example.com/inferred",
        published_at="2026-07-01",
    )
    overridden = inferred.model_copy(
        update={
            "id": "override",
            "title": "졸업요건 안내",
            "content": "졸업요건을 확인하세요.",
            "topic_key": "course",
        }
    )

    report = audit_posts(
        [inferred, overridden],
        catalog=rules,
        required_sources=("kumoh",),
        stale_after_days=180,
        generated_at=datetime(2026, 7, 13, tzinfo=UTC),
    )

    mismatch_ids = {
        issue.post_id for issue in report.issues if issue.code == "topic_override_mismatch"
    }
    assert mismatch_ids == {"override"}


def test_audit_does_not_require_a_post_for_the_default_fallback_topic() -> None:
    report = audit_posts(
        [post("only-course")],
        catalog=catalog(),
        required_sources=("kumoh",),
        stale_after_days=180,
        generated_at=datetime(2025, 8, 8, tzinfo=UTC),
    )

    empty_topics = {
        issue.topic_key for issue in report.issues if issue.code == "empty_topic"
    }
    assert "graduation" in empty_topics
    assert "general" not in empty_topics


def test_audit_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="비어"):
        audit_posts(
            [],
            catalog=catalog(),
            required_sources=("kumoh",),
            stale_after_days=180,
        )
