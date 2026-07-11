from __future__ import annotations

import re

from backend.app.domain import AnswerSource, RetrievedChunk
from backend.app.openai_service import AIProvider
from backend.app.schemas import ChatResponse
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
    ) -> None:
        self.provider = provider
        self.vector_store = vector_store
        self.top_k = top_k
        self.min_score = min_score

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
    def _rerank(question: str, items: list[RetrievedChunk]) -> list[RetrievedChunk]:
        terms = {
            term.lower()
            for term in re.findall(r"[0-9A-Za-z가-힣]{2,}", question)
            if term.lower() not in QUERY_STOP_WORDS
        }
        reranked: list[RetrievedChunk] = []
        for item in items:
            normalized_title = re.sub(r"\s+", "", item.chunk.title.lower())
            title_hits = sum(1 for term in terms if term in normalized_title)
            reranked.append(
                item.model_copy(update={"score": min(1.0, item.score + 0.08 * title_hits)})
            )
        return sorted(reranked, key=lambda item: item.score, reverse=True)

    def ask(self, question: str) -> ChatResponse:
        query_embedding = self.provider.embed([question])[0]
        retrieved = self._rerank(
            question, self.vector_store.query(query_embedding, self.top_k)
        )
        candidates = [item for item in retrieved if item.score >= self.min_score]
        best_score = max((item.score for item in candidates), default=0.0)
        relevant = [item for item in candidates if item.score >= best_score * 0.75]
        if not relevant:
            return ChatResponse(answer=NO_ANSWER, sources=[], grounded=False)
        answer = self.provider.answer(question, relevant)
        return ChatResponse(answer=answer, sources=self._sources(relevant), grounded=True)
