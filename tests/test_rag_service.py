from pathlib import Path

from rag_chatbot.document_loader import KnowledgeDocument
from rag_chatbot.rag_service import RagService


def test_answer_returns_relevant_source() -> None:
    documents = [
        KnowledgeDocument(
            id="graduation",
            title="졸업 요건",
            audience="재학생",
            source_urls=["https://example.com/graduation"],
            last_checked="2026-07-07",
            owner="관리자",
            keywords=["졸업요건", "졸업학점"],
            body="## 요약\n\n졸업에 필요한 학점과 필수 과목을 안내한다.",
            path=Path("graduation.md"),
        ),
        KnowledgeDocument(
            id="events",
            title="학과 행사",
            audience="신입생",
            source_urls=["https://example.com/events"],
            last_checked="2026-07-07",
            owner="관리자",
            keywords=["행사", "오리엔테이션"],
            body="## 요약\n\n오리엔테이션과 학과 행사를 안내한다.",
            path=Path("events.md"),
        ),
    ]

    service = RagService(documents=documents, top_k=2)

    response = service.answer("졸업 요건과 졸업학점 알려줘")

    assert response.sources[0].id == "graduation"
    assert "졸업 요건" in response.answer


def test_answer_uses_chroma_index_after_rebuild(tmp_path: Path) -> None:
    documents = [
        KnowledgeDocument(
            id="graduation",
            title="졸업 요건",
            audience="재학생",
            source_urls=["https://example.com/graduation"],
            last_checked="2026-07-07",
            owner="관리자",
            keywords=["졸업요건", "졸업학점"],
            body="## 요약\n\n졸업에는 전공 학점과 필수 과목 이수가 필요합니다.",
            path=Path("graduation.md"),
        ),
        KnowledgeDocument(
            id="events",
            title="학과 행사",
            audience="신입생",
            source_urls=["https://example.com/events"],
            last_checked="2026-07-07",
            owner="관리자",
            keywords=["행사", "오리엔테이션"],
            body="## 요약\n\n오리엔테이션과 학과 행사를 안내한다.",
            path=Path("events.md"),
        ),
    ]

    service = RagService(
        documents=documents,
        top_k=1,
        chroma_dir=tmp_path / "chroma",
        collection_name="test_service",
    )

    stats = service.rebuild_index()
    response = service.answer("졸업학점과 필수 과목 알려줘")

    assert stats.document_count == 2
    assert stats.chunk_count >= 2
    assert response.sources[0].id == "graduation"
    assert response.sources[0].chunk_id == "graduation:0"
    assert "졸업에는 전공 학점" in response.answer
