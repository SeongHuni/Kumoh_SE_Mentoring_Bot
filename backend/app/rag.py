from __future__ import annotations

import math
from dataclasses import asdict
from numbers import Real

from backend.app.context_compressor import compress_contexts
from backend.app.domain import AnswerSource, BoardPost, RetrievedChunk
from backend.app.freshness import latest_intent_post
from backend.app.freshness_selector import select_freshest
from backend.app.hybrid_retriever import HybridRetriever
from backend.app.intent_analysis import (
    IntentAnalysis,
    IntentOption,
    analyze_intents,
    validate_confirmation,
)
from backend.app.openai_service import AIProvider
from backend.app.query_intent import analyze_query
from backend.app.query_planner import build_query_plan
from backend.app.recommendations import recent_notices, suggested_questions
from backend.app.relevance_gate import evaluate_candidates, relevant_candidates
from backend.app.request_evidence import supports_specific_request
from backend.app.reranker import rerank, to_retrieved
from backend.app.schemas import ChatResponse, ClarificationOption
from backend.app.topic_rules import IntentRule, TopicCatalog, TopicRule
from backend.app.vector_store import ChromaVectorStore

NO_ANSWER = (
    "수집된 게시글에서는 질문에 대한 근거를 찾지 못했습니다. "
    "질문을 조금 더 구체적으로 바꾸거나 원문 게시판을 직접 확인해 주세요."
)
CLARIFICATION = "질문 의도를 이렇게 이해했습니다. 무엇을 찾을지 선택해 주세요."

NOTICE_KIND_COMPATIBILITY: dict[str, frozenset[str]] = {
    "application": frozenset({"application", "guide"}),
    "policy": frozenset({"policy", "guide"}),
    "event": frozenset({"event", "guide"}),
    "guide": frozenset({"guide", "application", "policy"}),
}


def _intent_payload(intent: IntentOption) -> ClarificationOption:
    return ClarificationOption(**asdict(intent))


def _clarification_response(analysis: IntentAnalysis) -> ChatResponse:
    return ChatResponse(
        response_type="clarification",
        answer=CLARIFICATION,
        sources=[],
        grounded=False,
        interpreted_intent=_intent_payload(analysis.primary),
        clarification_options=[_intent_payload(option) for option in analysis.options],
        suggested_questions=[],
        recent_notices=[],
    )


def _intent_rule(topic: TopicRule, intent_key: str) -> IntentRule:
    rule = next((item for item in topic.intents if item.key == intent_key), None)
    if rule is None:
        raise ValueError(f"확인된 intent 규칙을 찾을 수 없습니다: {intent_key}")
    return rule


def _validate_top_k(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("top_k must be a positive integer")
    return value


def _validate_min_score(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("min_score must be a finite nonnegative number")
    score = float(value)
    if not math.isfinite(score) or score < 0:
        raise ValueError("min_score must be a finite nonnegative number")
    return score


def _matches_requested_notice_kind(
    candidate_kind: str | None,
    requested_kind: str | None,
) -> bool:
    """Keep generic notices broad, but do not substitute a different notice type."""

    if (
        requested_kind is None
        or requested_kind == "information"
        or candidate_kind is None
    ):
        return True
    allowed = NOTICE_KIND_COMPATIBILITY.get(requested_kind, {requested_kind})
    return candidate_kind in allowed


class RAGService:
    def __init__(
        self,
        *,
        provider: AIProvider,
        vector_store: ChromaVectorStore,
        top_k: int = 5,
        min_score: float = 0.2,
        topic_catalog: TopicCatalog | None = None,
        posts: list[BoardPost] | None = None,
    ) -> None:
        if topic_catalog is None:
            raise ValueError("accuracy-first RAG requires a TopicCatalog")
        self.provider = provider
        self.vector_store = vector_store
        self.top_k = _validate_top_k(top_k)
        self.min_score = _validate_min_score(min_score)
        self.topic_catalog = topic_catalog
        self.posts = list(posts) if posts is not None else []

        # 정확도를 우선해 최종 표시 수보다 넓은 후보군을 두 검색기에 동일하게 제공한다.
        candidate_k = max(self.top_k * 10, 50)
        self.hybrid_retriever = HybridRetriever(
            provider,
            vector_store,
            lexical_top_k=candidate_k,
            dense_top_k=candidate_k,
        )

    @staticmethod
    def _sources(items: list[RetrievedChunk]) -> list[AnswerSource]:
        sources: list[AnswerSource] = []
        seen_urls: set[str] = set()
        for item in items:
            if item.chunk.url in seen_urls:
                continue
            seen_urls.add(item.chunk.url)
            sources.append(
                AnswerSource(
                    title=item.chunk.title,
                    url=item.chunk.url,
                    source=item.chunk.source,
                    published_at=item.chunk.published_at,
                    score=round(item.score, 4),
                )
            )
        return sources

    def ask(
        self,
        question: str,
        *,
        confirmed_intent_key: str | None = None,
    ) -> ChatResponse:
        analysis = analyze_intents(question, self.topic_catalog)
        confirmed = (
            validate_confirmation(analysis, confirmed_intent_key)
            if confirmed_intent_key is not None
            else None
        )
        if confirmed is None:
            return _clarification_response(analysis)

        topic = self.topic_catalog.rule_for(confirmed.topic_key)
        if topic is None:
            raise ValueError(f"확인된 topic 규칙을 찾을 수 없습니다: {confirmed.topic_key}")
        intent_rule = _intent_rule(topic, confirmed.intent_key)
        query_intent = analyze_query(
            question,
            topic=topic,
            catalog=self.topic_catalog,
        )
        plan = build_query_plan(question, confirmed, query_intent)
        cross_topic_recent = confirmed.intent_key == "general.recent"
        hybrid = self.hybrid_retriever.retrieve(
            plan,
            topic_key=None if cross_topic_recent else confirmed.topic_key,
        )
        reranked = rerank(
            hybrid,
            confirmed,
            query_intent,
            intent_rule=intent_rule,
            allow_cross_topic=cross_topic_recent,
        )
        decisions = evaluate_candidates(reranked)
        relevant = [
            candidate
            for candidate in relevant_candidates(decisions)
            if candidate.score >= self.min_score
        ]
        requested_notice_kind = self.topic_catalog.classify_notice_kind(question, "")
        relevant = [
            candidate
            for candidate in relevant
            if _matches_requested_notice_kind(
                candidate.candidate.chunk.notice_kind,
                requested_notice_kind,
            )
        ]
        freshest = select_freshest(
            relevant,
            require_dated=query_intent.recency_requested,
        )
        canonical_latest = latest_intent_post(self.posts, confirmed.intent_key)
        if canonical_latest is not None:
            freshest = [
                candidate
                for candidate in freshest
                if candidate.candidate.chunk.url == canonical_latest.url
            ]
        selected = [
            candidate
            for candidate in freshest
            if supports_specific_request(
                candidate,
                question=question,
                query_intent=query_intent,
                intent_rule=intent_rule,
                policy=self.topic_catalog.retrieval_policy,
            )
        ][: self.top_k]

        suggestions = suggested_questions(self.topic_catalog, confirmed.topic_key)
        notices = recent_notices(
            self.posts,
            confirmed.topic_key,
            self.topic_catalog,
            intent_key=confirmed.intent_key,
        )
        interpreted = _intent_payload(confirmed)
        if not selected:
            return ChatResponse(
                response_type="no_answer",
                answer=NO_ANSWER,
                sources=[],
                grounded=False,
                interpreted_intent=interpreted,
                clarification_options=[],
                suggested_questions=suggestions,
                recent_notices=notices,
            )

        terms = tuple(
            dict.fromkeys(
                (
                    *query_intent.match_terms,
                    *query_intent.distinctive_terms,
                    *intent_rule.keywords,
                    *intent_rule.evidence_markers,
                )
            )
        )
        contexts = compress_contexts(to_retrieved(selected), terms=terms)
        answer = self.provider.answer(question, contexts)
        return ChatResponse(
            response_type="answer",
            answer=answer,
            sources=self._sources(contexts),
            grounded=True,
            interpreted_intent=interpreted,
            clarification_options=[],
            suggested_questions=suggestions,
            recent_notices=notices,
        )
