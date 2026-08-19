from __future__ import annotations

from collections import defaultdict

from backend.app.chroma_store import ChromaDataStore, RetrievedDocument
from backend.app.config import Settings
from backend.app.openai_service import OpenAIRagClient
from backend.app.schemas import ChatResponse

LECTURE_REVIEW_CATEGORY = "강의평"
LECTURE_REVIEW_SUBJECTS = ("교수", "강의", "수업")
LECTURE_REVIEW_SIGNALS = ("강의평", "평가", "후기", "리뷰", "어때", "난이도", "시험")


class RAGService:
    def __init__(self, settings: Settings, store: ChromaDataStore) -> None:
        self.client = OpenAIRagClient(settings)
        self.store = store
        self.top_k = settings.top_k
        self.category_probe_k = settings.category_probe_k

    @staticmethod
    def _select_category(documents: list[RetrievedDocument]) -> str | None:
        category_scores: defaultdict[str, float] = defaultdict(float)
        for rank, document in enumerate(documents, start=1):
            if document.category:
                category_scores[document.category] += max(document.source.score, 0.01) / rank
        return max(category_scores, key=category_scores.get) if category_scores else None

    @staticmethod
    def _explicit_category(question: str) -> str | None:
        normalized = "".join(question.split())
        has_subject = any(subject in normalized for subject in LECTURE_REVIEW_SUBJECTS)
        has_signal = any(signal in normalized for signal in LECTURE_REVIEW_SIGNALS)
        return LECTURE_REVIEW_CATEGORY if has_subject and has_signal else None

    def ask(self, question: str) -> ChatResponse:
        query_embedding = self.client.embed_query(question)
        explicit_category = self._explicit_category(question)
        candidates: list[RetrievedDocument] = []
        if explicit_category:
            documents = self.store.search(
                query_embedding,
                category=explicit_category,
                limit=self.top_k,
            )
        else:
            candidates = self.store.search(query_embedding, limit=self.category_probe_k)
            category = self._select_category(candidates)
            documents = (
                self.store.search(query_embedding, category=category, limit=self.top_k)
                if category
                else candidates[: self.top_k]
            )
        if not documents:
            if not candidates:
                candidates = self.store.search(query_embedding, limit=self.top_k)
            documents = candidates[: self.top_k]
        if not documents:
            return ChatResponse(
                response_type="no_answer",
                answer="Chroma 데이터에서 질문과 관련된 안내를 찾지 못했습니다.",
                sources=[],
                grounded=False,
            )

        # Chroma's similarity order is intentionally used as-is: no reranking is applied.
        answer = self.client.answer(question, documents)
        return ChatResponse(
            answer=answer,
            sources=[item.source for item in documents],
            grounded=True,
        )
