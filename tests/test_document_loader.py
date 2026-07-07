from pathlib import Path

from rag_chatbot.document_loader import load_knowledge_documents, load_markdown_document


def test_load_markdown_document_reads_metadata_and_body(tmp_path: Path) -> None:
    path = tmp_path / "sample.md"
    path.write_text(
        """---
id: sample
title: 샘플
audience: 신입생
source_urls:
  - https://example.com
last_checked: 2026-07-07
owner: 관리자
keywords: 샘플, 테스트
---

## 요약

샘플 문서입니다.
""",
        encoding="utf-8",
    )

    document = load_markdown_document(path)

    assert document.id == "sample"
    assert document.title == "샘플"
    assert document.source_urls == ["https://example.com"]
    assert document.keywords == ["샘플", "테스트"]
    assert "샘플 문서입니다" in document.body


def test_load_knowledge_documents_returns_sorted_markdown_files(tmp_path: Path) -> None:
    for name in ["b.md", "a.md"]:
        (tmp_path / name).write_text(
            f"""---
id: {name.removesuffix(".md")}
title: {name}
audience: 신입생
source_urls:
  - https://example.com
last_checked: 2026-07-07
owner: 관리자
keywords: 테스트
---

본문
""",
            encoding="utf-8",
        )

    documents = load_knowledge_documents(tmp_path)

    assert [document.id for document in documents] == ["a", "b"]

