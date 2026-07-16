from __future__ import annotations

from backend.app.query_intent import QueryIntent, compact
from backend.app.reranker import RerankedCandidate, contains_marker
from backend.app.topic_rules import IntentRule, RetrievalPolicy

# 이 intent들은 여러 하위 요청을 한 규칙으로 다루므로 topic 일치만으로는
# 근거가 충분하지 않다. 질문의 구체어까지 문서에서 확인해 과잉 응답을 막는다.
BROAD_INTENT_KEYS = frozenset(
    {"career.general", "scholarship.general", "general.recent"}
)
BOARD_SCOPE_TERMS = frozenset(
    {"학과", "전공", "소프트웨어전공", "컴퓨터공학부", "학교"}
)


def _meaningful_terms(query_intent: QueryIntent) -> tuple[str, ...]:
    ignored = {compact(term) for term in BOARD_SCOPE_TERMS}
    return tuple(
        term
        for term in query_intent.distinctive_terms
        if compact(term) not in ignored
    )


def _requested_markers(
    question: str,
    intent_rule: IntentRule,
    policy: RetrievalPolicy,
) -> tuple[str, ...]:
    normalized_question = compact(question)
    requested = [
        marker
        for marker in (*intent_rule.keywords, *intent_rule.evidence_markers)
        if compact(marker) in normalized_question
    ]
    for group in policy.alias_groups:
        if any(compact(marker) in normalized_question for marker in group):
            requested.extend(group)
    return tuple(dict.fromkeys(requested))


def supports_specific_request(
    candidate: RerankedCandidate,
    *,
    question: str,
    query_intent: QueryIntent,
    intent_rule: IntentRule,
    policy: RetrievalPolicy,
) -> bool:
    """Fail closed when a broad intent lacks evidence for the user's exact request."""

    if intent_rule.key not in BROAD_INTENT_KEYS:
        return True

    chunk = candidate.candidate.chunk
    evidence_text = f"{chunk.title}\n{chunk.text}"
    meaningful_terms = _meaningful_terms(query_intent)
    if meaningful_terms and not all(
        contains_marker(evidence_text, term) for term in meaningful_terms
    ):
        return False

    if intent_rule.key != "general.recent":
        requested_markers = _requested_markers(question, intent_rule, policy)
        if not requested_markers or not any(
            contains_marker(evidence_text, marker) for marker in requested_markers
        ):
            return False

    # 단순히 "최근 장학 공지"처럼 세부어가 없는 요청은 제목 자체가 해당
    # intent임을 보여야 한다. 본문의 우연한 단어 하나만으로 최신 공지가 되지 않는다.
    if not meaningful_terms:
        return candidate.title_marker_match
    return True
