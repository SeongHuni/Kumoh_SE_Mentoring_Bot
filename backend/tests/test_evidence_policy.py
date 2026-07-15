from backend.app.domain import RetrievedChunk, TextChunk
from backend.app.evidence_policy import decide_evidence
from backend.app.query_intent import QueryIntent
from backend.app.topic_rules import RetrievalPolicy, TopicCatalog, TopicRule


def chunk(title: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=TextChunk(
            id="kumoh:1:0",
            post_id="1",
            source="kumoh",
            title=title,
            text="본문은 근거 적합성 1차 판정에 사용하지 않습니다.",
            url="https://example.com/1",
            published_at="2026-03-19",
            chunk_index=0,
            topic_key="capstone",
            topic_label="캡스톤",
            is_latest_topic=True,
        ),
        score=0.9,
    )


def policy_catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        retrieval_policy=RetrievalPolicy(alias_groups=(("채용", "초빙"),)),
        rules=(
            TopicRule("capstone", "캡스톤", ("캡스톤",), (), ("캡스톤",)),
            TopicRule("career", "진로", ("채용",), (), ("초빙",)),
            TopicRule("general", "전체", (), ()),
        ),
    )


def intent(**updates) -> QueryIntent:
    values = {
        "topic_key": "capstone",
        "requested_year": None,
        "requested_term": None,
        "recency_requested": False,
        "match_terms": ("캡스톤",),
        "distinctive_terms": (),
    }
    values.update(updates)
    return QueryIntent(**values)


def test_rejects_conflicting_semester() -> None:
    catalog = policy_catalog()
    rule = catalog.rule_for("capstone")
    assert rule is not None

    decision = decide_evidence(
        intent(requested_year=2026, requested_term="second"),
        topic=rule,
        catalog=catalog,
        item=chunk("2026학년도 1학기 캡스톤 디자인 운영 계획"),
    )

    assert decision.accepted is False
    assert decision.reason == "semester_mismatch"


def test_accepts_alias_connected_title_marker() -> None:
    catalog = policy_catalog()
    rule = catalog.rule_for("career")
    assert rule is not None

    decision = decide_evidence(
        intent(
            topic_key="career",
            recency_requested=True,
            match_terms=("채용", "초빙"),
        ),
        topic=rule,
        catalog=catalog,
        item=chunk("2026년 하반기 전임교원 초빙 공개강의 심사 공고"),
    )

    assert decision.accepted is True
    assert decision.reason == "accepted_topic_marker"


def test_rejects_unrelated_latest_topic_title() -> None:
    catalog = policy_catalog()
    rule = TopicRule("scholarship", "장학", ("장학",), (), ("장학",))

    decision = decide_evidence(
        intent(
            topic_key="scholarship",
            match_terms=("장학금", "신청"),
            distinctive_terms=("신청",),
        ),
        topic=rule,
        catalog=catalog,
        item=chunk("방산AI인재양성부트캠프사업단 설명회 안내"),
    )

    assert decision.accepted is False
    assert decision.reason == "insufficient_title_evidence"


def test_accepts_single_strong_distinctive_title_term() -> None:
    catalog = policy_catalog()
    rule = catalog.rule_for("general")
    assert rule is not None

    decision = decide_evidence(
        intent(
            topic_key="general",
            match_terms=("소프트웨어전공",),
            distinctive_terms=("소프트웨어전공",),
        ),
        topic=rule,
        catalog=catalog,
        item=chunk("소프트웨어전공 전임교원 초빙 공개강의 심사 공고"),
    )

    assert decision.accepted is True
    assert decision.reason == "accepted_title_overlap"


def test_requires_explicit_title_date_for_specific_period() -> None:
    catalog = policy_catalog()
    rule = catalog.rule_for("capstone")
    assert rule is not None

    decision = decide_evidence(
        intent(requested_year=2026, requested_term="first"),
        topic=rule,
        catalog=catalog,
        item=chunk("캡스톤 디자인 운영 계획"),
    )

    assert decision.reason == "missing_temporal_evidence"
