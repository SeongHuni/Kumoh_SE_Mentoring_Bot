from backend.app.query_intent import analyze_query
from backend.app.topic_rules import RetrievalPolicy, TopicCatalog, TopicRule


def catalog() -> TopicCatalog:
    return TopicCatalog(
        default_topic_key="general",
        retrieval_policy=RetrievalPolicy(
            recency_terms=("최근", "최신"),
            generic_terms=("공지", "알려줘", "찾아줘", "언제"),
            alias_groups=(("채용", "초빙"),),
        ),
        rules=(
            TopicRule("career", "진로·취업", ("채용", "취업"), (), ("초빙",)),
            TopicRule("capstone", "캡스톤", ("캡스톤디자인", "캡스톤 디자인"), ()),
            TopicRule("registration", "수강신청", ("수강신청", "수강 신청"), ()),
            TopicRule("general", "전체", (), ()),
        ),
    )


def test_analyze_query_extracts_year_and_academic_term() -> None:
    rules = catalog()
    topic = rules.rule_for("capstone")
    assert topic is not None

    intent = analyze_query(
        "2026학년도 2학기 캡스톤디자인 공지를 알려줘",
        topic=topic,
        catalog=rules,
    )

    assert intent.topic_key == "capstone"
    assert intent.requested_year == 2026
    assert intent.requested_term == "second"
    assert intent.recency_requested is False


def test_analyze_query_expands_alias_terms_for_title_matching() -> None:
    rules = catalog()
    topic = rules.rule_for("career")
    assert topic is not None

    intent = analyze_query("최근 채용 공지를 찾아줘", topic=topic, catalog=rules)

    assert intent.recency_requested is True
    assert "채용" in intent.match_terms
    assert "초빙" in intent.match_terms


def test_analyze_query_keeps_only_distinctive_terms() -> None:
    rules = catalog()
    topic = rules.rule_for("registration")
    assert topic is not None

    intent = analyze_query("수강 신청 기간은 언제야?", topic=topic, catalog=rules)

    assert "기간" in intent.distinctive_terms
    assert "수강" not in intent.distinctive_terms
    assert "신청" not in intent.distinctive_terms


def test_analyze_query_distinguishes_summer_term() -> None:
    rules = catalog()
    topic = rules.rule_for("registration")
    assert topic is not None

    intent = analyze_query("2026학년도 여름계절수업 안내", topic=topic, catalog=rules)

    assert intent.requested_year == 2026
    assert intent.requested_term == "summer"
