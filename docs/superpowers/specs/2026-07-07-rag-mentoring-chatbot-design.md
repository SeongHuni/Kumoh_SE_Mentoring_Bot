# RAG Mentoring Chatbot Design

## Goal

Build a maintainable RAG foundation for a department introduction and mentoring chatbot.

## Users

Primary users are incoming students, prospective students, returning students, and transfer students. Secondary users are current students.

## Knowledge Scope

The initial knowledge base is split into ten Markdown topics: department introduction, curriculum, professors, graduation requirements, scholarships, extracurricular programs, employment status, FAQ, academic notices, and department events. Markdown files act as seed data and a human-readable maintenance format. A later version will store knowledge in a database.

## Architecture

The application uses Python, FastAPI, Markdown seed files, Chroma, and a vector-store-ready retrieval boundary. Markdown files are loaded from `data/knowledge`, normalized into typed documents, chunked, indexed in Chroma, searched through an index interface, and returned through a RAG service. Later, a database repository can return the same typed document shape without changing the API contract. The first implementation uses deterministic local hash embeddings and returns grounded answer drafts from retrieved chunks so the server can be verified before an LLM key is added.

## Maintenance Rules

Each Markdown file includes source URL, last checked date, admin notes, and search keywords. Maintainers update topic files directly during the prototype phase. In the DB-backed phase, Markdown can be imported into database records and maintained through scripts or an admin interface.

## Success Criteria

- The project installs in a local Python virtual environment.
- The API starts with `uvicorn rag_chatbot.main:app --reload`.
- The `/index/rebuild` endpoint indexes Markdown seed documents into Chroma.
- The `/chat` endpoint returns relevant chunks and source metadata.
- Tests cover Markdown loading and basic retrieval behavior.
