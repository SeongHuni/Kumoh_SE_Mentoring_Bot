from pathlib import Path

from rag_chatbot.document_loader import KnowledgeDocument
from rag_chatbot.schemas import ChatResponse, Source
from rag_chatbot.vector_store import ChromaKnowledgeIndex, IndexStats, LocalKnowledgeIndex


class RagService:
    def __init__(
        self,
        documents: list[KnowledgeDocument],
        top_k: int = 4,
        chroma_dir: Path | None = None,
        collection_name: str = "department_knowledge",
    ):
        self.documents = documents
        self.top_k = top_k
        self.local_index = LocalKnowledgeIndex(documents)
        self.chroma_index = (
            ChromaKnowledgeIndex(
                documents=documents,
                persist_directory=chroma_dir,
                collection_name=collection_name,
            )
            if chroma_dir
            else None
        )
        self._index_ready = False

    def rebuild_index(self) -> IndexStats:
        if not self.chroma_index:
            return IndexStats(document_count=len(self.documents), chunk_count=len(self.documents))
        stats = self.chroma_index.rebuild()
        self._index_ready = True
        return stats

    def answer(self, question: str) -> ChatResponse:
        if self.chroma_index:
            if not self._index_ready:
                self.rebuild_index()
            matches = self.chroma_index.search(question, self.top_k)
            return self._answer_from_chunks(matches)

        matches = self.local_index.search(question, self.top_k)
        return self._answer_from_documents(matches)

    def _answer_from_documents(
        self,
        matches: list[tuple[KnowledgeDocument, float]],
    ) -> ChatResponse:
        if not matches:
            return self._empty_answer()

        lead = matches[0][0]
        answer = (
            f"질문과 가장 관련 있는 항목은 '{lead.title}'입니다. "
            f"{self._first_summary_sentence(lead)} "
            "정확한 일정, 금액, 학번별 예외는 아래 출처의 최신 공지를 기준으로 확인해야 합니다."
        )

        return ChatResponse(
            answer=answer,
            sources=[
                Source(
                    id=document.id,
                    title=document.title,
                    source_urls=document.source_urls,
                    last_checked=document.last_checked,
                    score=round(score, 4),
                    excerpt=self._first_summary_sentence(document),
                )
                for document, score in matches
            ],
        )

    def _answer_from_chunks(self, matches) -> ChatResponse:
        if not matches:
            return self._empty_answer()

        lead = matches[0]
        lead_document = lead.document
        answer = (
            f"질문과 가장 관련 있는 항목은 '{lead_document.title}'입니다. "
            f"{self._first_chunk_sentence(lead.chunk.text, lead_document.title)} "
            "정확한 일정, 금액, 학번별 예외는 아래 출처의 최신 공지를 기준으로 확인해야 합니다."
        )

        return ChatResponse(
            answer=answer,
            sources=[
                Source(
                    id=match.document.id,
                    title=match.document.title,
                    source_urls=match.document.source_urls,
                    last_checked=match.document.last_checked,
                    score=match.score,
                    chunk_id=match.chunk.chunk_id,
                    excerpt=self._first_chunk_sentence(match.chunk.text, match.document.title),
                )
                for match in matches
            ],
        )

    @staticmethod
    def _empty_answer() -> ChatResponse:
        return ChatResponse(
            answer=(
                "관련 문서를 찾지 못했습니다. 질문을 더 구체적으로 작성하거나 "
                "학과 공식 사이트와 내부 사이트의 최신 공지를 확인해 주세요."
            ),
            sources=[],
        )

    @staticmethod
    def _first_summary_sentence(document: KnowledgeDocument) -> str:
        for line in document.body.splitlines():
            cleaned = line.strip("- ").strip()
            if cleaned and not cleaned.startswith("#"):
                return cleaned
        return "해당 문서의 요약을 참고해 주세요."

    @staticmethod
    def _first_chunk_sentence(text: str, title: str | None = None) -> str:
        for line in text.splitlines():
            cleaned = line.strip("- ").strip()
            if not cleaned:
                continue
            if cleaned == title:
                continue
            if cleaned.startswith("#") or cleaned.startswith("대상:") or cleaned.startswith("키워드:"):
                continue
            if cleaned:
                return cleaned
        return "검색된 문서 조각을 참고해 주세요."
