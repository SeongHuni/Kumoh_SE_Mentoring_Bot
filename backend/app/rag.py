from __future__ import annotations

import re
from datetime import UTC, datetime

from backend.app.domain import AnswerSource, BoardPost, RetrievedChunk
from backend.app.freshness import parse_published_at
from backend.app.openai_service import AIProvider
from backend.app.recommendations import recent_notices, suggested_questions
from backend.app.schemas import ChatResponse
from backend.app.topic_rules import TopicCatalog
from backend.app.vector_store import ChromaVectorStore

NO_ANSWER = (
    "수집된 게시글에서는 질문에 대한 근거를 찾지 못했습니다. "
    "질문을 조금 더 구체적으로 바꾸거나 원문 게시판을 직접 확인해 주세요."
)
# "신청"/"학과"는 공지 제목 대부분에 등장하는 범용 어휘라 특정 문서를 가리키는
# 신호로 쓰기에는 너무 흔하다("출석인정신청"처럼 무관한 문서에도 부분 문자열로 매칭됨).
QUERY_STOP_WORDS = {
    "공지를",
    "알려줘",
    "찾아줘",
    "관련",
    "방법",
    "뭐야",
    "최근",
    "신청",
    "학과",
}
# 같은 개념을 가리키는 학사 공지 특유의 표현 차이를 보정하기 위한 좁은 동의어 목록.
TERM_SYNONYMS: dict[str, tuple[str, ...]] = {"채용": ("초빙",)}
YEAR_PATTERN = re.compile(r"(\d{4})학년도")
SEMESTER_PATTERN = re.compile(r"(\d)학기")


def _extract_period(text: str) -> tuple[str | None, str | None]:
    year_match = YEAR_PATTERN.search(text)
    semester_match = SEMESTER_PATTERN.search(text)
    return (
        year_match.group(1) if year_match else None,
        semester_match.group(1) if semester_match else None,
    )


def _conflicts_with_period(question: str, candidate_text: str) -> bool:
    """질문이 특정 학년도·학기를 지정했는데 후보 문서가 다른 학년도·학기를 명시하면 충돌로 본다."""
    query_year, query_semester = _extract_period(question)
    if query_year is None and query_semester is None:
        return False
    candidate_year, candidate_semester = _extract_period(candidate_text)
    if query_year and candidate_year and query_year != candidate_year:
        return True
    return bool(query_semester and candidate_semester and query_semester != candidate_semester)


def _content_terms(question: str) -> set[str]:
    return {
        term.lower()
        for term in re.findall(r"[0-9A-Za-z가-힣]{2,}", question)
        if term.lower() not in QUERY_STOP_WORDS
    }


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
    def _rerank(question: str, items: list[RetrievedChunk]) -> list[RetrievedChunk]:
        terms = _content_terms(question)
        expanded_terms = set(terms)
        for term in terms:
            expanded_terms.update(TERM_SYNONYMS.get(term, ()))
        reranked: list[RetrievedChunk] = []
        for item in items:
            normalized_title = re.sub(r"\s+", "", item.chunk.title.lower())
            title_hits = sum(1 for term in expanded_terms if term in normalized_title)
            reranked.append(
                item.model_copy(update={"score": min(1.0, item.score + 0.08 * title_hits)})
            )
        return sorted(reranked, key=lambda item: item.score, reverse=True)

    def ask(self, question: str) -> ChatResponse:
        topic = self.topic_catalog.classify(question) if self.topic_catalog else None
        query_embedding = self.provider.embed([question])[0]
        where = None
        if topic is not None:
            where = {"is_latest_topic": True}
            if topic.key != self.topic_catalog.default_topic_key:
                where = {
                    "$and": [
                        {"is_latest_topic": True},
                        {"topic_key": topic.key},
                    ]
                }
        fetched = self.vector_store.query(query_embedding, self.top_k, where=where)
        fetched = [
            item
            for item in fetched
            if not _conflicts_with_period(question, f"{item.chunk.title} {item.chunk.text}")
        ]
        retrieved = self._rerank(question, fetched)
        candidates = [item for item in retrieved if item.score >= self.min_score]
        best_score = max((item.score for item in candidates), default=0.0)
        relevant = [item for item in candidates if item.score >= best_score * 0.75]
        if (
            not relevant
            and fetched
            and topic is not None
            and self.topic_catalog is not None
            and topic.key == self.topic_catalog.default_topic_key
            and not _content_terms(question)
        ):
            # 특정 내용어 없이 "최근 학과 공지"류로 묻는 경우, 임계값 미달이어도
            # 가장 최신 게시글을 근거로 답한다.
            newest = max(
                fetched,
                key=lambda item: parse_published_at(item.chunk.published_at)
                or datetime.min.replace(tzinfo=UTC),
            )
            relevant = [newest]
        suggestions = (
            suggested_questions(self.topic_catalog, topic.key) if topic else []
        )
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
