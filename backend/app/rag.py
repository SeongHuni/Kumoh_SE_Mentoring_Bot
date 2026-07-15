from __future__ import annotations

import re

from backend.app.domain import AnswerSource, BoardPost, RetrievedChunk
from backend.app.evidence_policy import decide_evidence
from backend.app.freshness import freshness_key
from backend.app.openai_service import AIProvider
from backend.app.query_intent import QueryIntent, analyze_query, compact
from backend.app.recommendations import recent_notices, suggested_questions
from backend.app.schemas import ChatResponse
from backend.app.topic_rules import TopicCatalog
from backend.app.vector_store import ChromaVectorStore

NO_ANSWER = (
    "수집된 게시글에서는 질문에 대한 근거를 찾지 못했습니다. "
    "질문을 조금 더 구체적으로 바꾸거나 원문 게시판을 직접 확인해 주세요."
)
QUERY_STOP_WORDS = {"공지를", "알려줘", "찾아줘", "관련", "방법", "뭐야", "최근"}


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
        self.provider = provider
        self.vector_store = vector_store
        self.top_k = top_k
        self.min_score = min_score
        self.topic_catalog = topic_catalog
        self.posts = posts if posts is not None else []

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

    @staticmethod
    def _rerank(
        question: str,
        items: list[RetrievedChunk],
        intent: QueryIntent | None = None,
    ) -> list[RetrievedChunk]:
        terms = {
            term.lower()
            for term in re.findall(r"[0-9A-Za-z가-힣]{2,}", question)
            if term.lower() not in QUERY_STOP_WORDS
        }
        match_terms = intent.match_terms if intent else ()
        reranked: list[RetrievedChunk] = []
        for item in items:
            normalized_title = compact(item.chunk.title)
            lexical_hits = sum(1 for term in terms if compact(term) in normalized_title)
            policy_hits = sum(
                1
                for term in match_terms
                if 2 <= len(term) <= len(normalized_title) and term in normalized_title
            )
            boost = 0.08 * lexical_hits + min(0.24, 0.12 * policy_hits)
            reranked.append(
                item.model_copy(update={"score": min(1.0, item.score + boost)})
            )
        return sorted(reranked, key=lambda item: item.score, reverse=True)

    def _general_latest_url(self) -> str | None:
        latest = [post for post in self.posts if post.is_latest_topic]
        if not latest:
            return None
        return max(latest, key=freshness_key).url

    def ask(self, question: str) -> ChatResponse:
        topic = self.topic_catalog.classify(question) if self.topic_catalog else None
        intent = (
            analyze_query(question, topic=topic, catalog=self.topic_catalog)
            if topic is not None and self.topic_catalog is not None
            else None
        )
        query_embedding = self.provider.embed([question])[0]
        where = None
        if topic is not None and self.topic_catalog is not None:
            where_parts: list[dict[str, object]] = [{"is_latest_topic": True}]
            if topic.key != self.topic_catalog.default_topic_key:
                where_parts.append({"topic_key": topic.key})
            elif intent is not None and intent.recency_requested:
                latest_url = self._general_latest_url()
                if latest_url is not None:
                    where_parts.append({"url": latest_url})
            where = where_parts[0] if len(where_parts) == 1 else {"$and": where_parts}

        retrieved = self._rerank(
            question,
            self.vector_store.query(query_embedding, self.top_k, where=where),
            intent,
        )
        policy_enabled = bool(
            topic is not None
            and self.topic_catalog is not None
            and intent is not None
            and (
                topic.evidence_markers
                or self.topic_catalog.retrieval_policy.recency_terms
                or self.topic_catalog.retrieval_policy.alias_groups
            )
        )
        accepted: list[tuple[RetrievedChunk, str]] = []
        for item in retrieved:
            if not policy_enabled:
                accepted.append((item, "legacy"))
                continue
            decision = decide_evidence(
                intent,
                topic=topic,
                catalog=self.topic_catalog,
                item=item,
            )
            if decision.accepted:
                accepted.append((item, decision.reason))

        candidates = [
            item
            for item, reason in accepted
            if item.score >= self.min_score or reason == "accepted_general_latest"
        ]
        best_score = max((item.score for item in candidates), default=0.0)
        relevant = [
            item
            for item in candidates
            if best_score == 0.0 or item.score >= best_score * 0.75
        ]
        suggestions = suggested_questions(self.topic_catalog, topic.key) if topic else []
        notices = recent_notices(self.posts, topic.key, self.topic_catalog) if topic else []
        if not relevant:
            return ChatResponse(
                answer=NO_ANSWER,
                sources=[],
                grounded=False,
                suggested_questions=suggestions,
                recent_notices=notices,
            )
        answer = self.provider.answer(question, relevant)
        return ChatResponse(
            answer=answer,
            sources=self._sources(relevant),
            grounded=True,
            suggested_questions=suggestions,
            recent_notices=notices,
        )
