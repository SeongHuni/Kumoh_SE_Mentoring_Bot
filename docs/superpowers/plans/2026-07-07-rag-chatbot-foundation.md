# RAG Chatbot Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a runnable FastAPI RAG chatbot foundation backed by maintainable topic-based Markdown files.

**Architecture:** Markdown files are loaded into typed documents, indexed through a retrieval boundary, and exposed through FastAPI endpoints. The initial answer generator returns grounded source-based drafts and can later be replaced by an LLM call.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, Chroma dependency, pytest.

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `README.md`

- [x] Add package metadata, dependencies, and pytest configuration.
- [x] Add local environment defaults.
- [x] Document setup, run, and test commands.

### Task 2: Knowledge Documents

**Files:**
- Create: `data/knowledge/*.md`
- Create: `docs/rag-chatbot-design.md`

- [x] Create ten topic-based Markdown files.
- [x] Include source URL, last checked date, admin notes, and keywords in every file.
- [x] Write a short design document that records target users, scope, and architecture.

### Task 3: Application Code

**Files:**
- Create: `src/rag_chatbot/config.py`
- Create: `src/rag_chatbot/document_loader.py`
- Create: `src/rag_chatbot/vector_store.py`
- Create: `src/rag_chatbot/rag_service.py`
- Create: `src/rag_chatbot/main.py`

- [x] Implement settings.
- [x] Implement Markdown document loading.
- [x] Implement a deterministic local search index.
- [x] Implement the RAG service.
- [x] Expose health, document listing, and chat endpoints.

### Task 4: Verification

**Files:**
- Create: `tests/test_document_loader.py`
- Create: `tests/test_rag_service.py`

- [x] Test Markdown loading.
- [x] Test chat response retrieval.
- [x] Install dependencies in a virtual environment.
- [x] Run pytest.

