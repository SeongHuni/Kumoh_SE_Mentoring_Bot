from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from backend.app.domain import BoardPost
from backend.app.freshness import parse_published_at
from backend.app.topic_classifier import enrich_posts
from backend.app.topic_rules import TopicCatalog


class AuditIssue(BaseModel):
    code: str
    message: str
    source: str | None = None
    topic_key: str | None = None
    post_id: str | None = None
    title: str | None = None
    url: str | None = None


class TopicAuditSummary(BaseModel):
    topic_key: str
    topic_label: str
    post_count: int
    latest_title: str | None
    latest_url: str | None
    latest_published_at: str | None


class DataAuditReport(BaseModel):
    generated_at: datetime
    stale_after_days: int
    total_posts: int
    source_counts: dict[str, int]
    topic_summaries: list[TopicAuditSummary]
    issues: list[AuditIssue]


def audit_posts(
    posts: Iterable[BoardPost],
    *,
    catalog: TopicCatalog,
    required_sources: tuple[str, ...],
    stale_after_days: int,
    generated_at: datetime | None = None,
) -> DataAuditReport:
    post_list = list(posts)
    if not post_list:
        raise ValueError("감사할 게시글 데이터가 비어 있습니다.")
    if stale_after_days < 1:
        raise ValueError("stale-after-days는 1 이상이어야 합니다.")
    now = generated_at or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    enriched = enrich_posts(post_list, catalog)
    source_counts = dict(sorted(Counter(post.source for post in enriched).items()))
    issues: list[AuditIssue] = []

    for source in required_sources:
        if source not in source_counts:
            issues.append(
                AuditIssue(
                    code="missing_source",
                    source=source,
                    message=f"필수 source가 없습니다: {source}",
                )
            )

    for post in enriched:
        if parse_published_at(post.published_at) is None:
            issues.append(
                AuditIssue(
                    code="missing_published_at",
                    source=post.source,
                    topic_key=post.topic_key,
                    post_id=post.id,
                    title=post.title,
                    url=post.url,
                    message="게시일이 없거나 ISO 날짜로 해석되지 않습니다.",
                )
            )
        if post.topic_key and catalog.rule_for(post.topic_key):
            classified = catalog.classify(f"{post.title}\n{post.content}").key
            if classified != post.topic_key:
                issues.append(
                    AuditIssue(
                        code="topic_override_mismatch",
                        source=post.source,
                        topic_key=post.topic_key,
                        post_id=post.id,
                        title=post.title,
                        url=post.url,
                        message=(
                            f"규칙 분류는 {classified}이지만 override는 "
                            f"{post.topic_key}입니다."
                        ),
                    )
                )

    summaries: list[TopicAuditSummary] = []
    for rule in catalog.rules:
        topic_posts = [post for post in enriched if post.topic_key == rule.key]
        latest = next((post for post in topic_posts if post.is_latest_topic), None)
        summaries.append(
            TopicAuditSummary(
                topic_key=rule.key,
                topic_label=rule.label,
                post_count=len(topic_posts),
                latest_title=latest.title if latest else None,
                latest_url=latest.url if latest else None,
                latest_published_at=latest.published_at if latest else None,
            )
        )
        if latest is None:
            issues.append(
                AuditIssue(
                    code="empty_topic",
                    topic_key=rule.key,
                    message=f"주제에 게시글이 없습니다: {rule.key}",
                )
            )
            continue
        published = parse_published_at(latest.published_at)
        if published is not None and now - published > timedelta(days=stale_after_days):
            issues.append(
                AuditIssue(
                    code="stale_topic",
                    source=latest.source,
                    topic_key=rule.key,
                    post_id=latest.id,
                    title=latest.title,
                    url=latest.url,
                    message=f"최신 게시일이 {stale_after_days}일 기준보다 오래됐습니다.",
                )
            )

    return DataAuditReport(
        generated_at=now,
        stale_after_days=stale_after_days,
        total_posts=len(enriched),
        source_counts=source_counts,
        topic_summaries=summaries,
        issues=issues,
    )


def render_markdown(report: DataAuditReport) -> str:
    lines = [
        "# Data Audit Report",
        "",
        f"- Generated at: {report.generated_at.isoformat()}",
        f"- Total posts: {report.total_posts}",
        f"- Issues: {len(report.issues)}",
        "",
        "## Sources",
        "",
        "| Source | Posts |",
        "| --- | ---: |",
    ]
    lines.extend(
        f"| {source} | {count} |" for source, count in report.source_counts.items()
    )
    lines.extend(
        [
            "",
            "## Topics",
            "",
            "| Topic | Posts | Latest title | Latest date | URL |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for summary in report.topic_summaries:
        lines.append(
            f"| {summary.topic_key} | {summary.post_count} | "
            f"{summary.latest_title or '-'} | {summary.latest_published_at or '-'} | "
            f"{summary.latest_url or '-'} |"
        )
    lines.extend(["", "## Issues", ""])
    lines.extend(
        f"- [{issue.code}] {issue.message}"
        + (f" · {issue.title}" if issue.title else "")
        + (f" · {issue.url}" if issue.url else "")
        for issue in report.issues
    )
    if not report.issues:
        lines.append("- 없음")
    return "\n".join(lines).rstrip() + "\n"
