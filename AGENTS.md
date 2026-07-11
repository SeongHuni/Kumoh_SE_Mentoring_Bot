# Repository Guidelines

## Project Structure & Module Organization

The repository contains `SE_mentorbot_주제제안서_v1.2.pptx`, the proposal for SE Mentor Bot, a source-citing RAG assistant for Software Engineering students. Keep planning artifacts at the root until implementation is scaffolded.

Use the following layout as code is added:

- `frontend/`: Next.js chat UI; colocate component tests with components.
- `backend/app/`: FastAPI routes, RAG orchestration, retrieval, and source citation logic.
- `backend/tests/`: Python unit and integration tests.
- `data/raw/`: immutable crawled official documents; `data/processed/`: normalized chunks and metadata.
- `docs/`: architecture notes and evaluations.

Do not commit generated vector indexes, local databases, build output, or secrets.

## Build, Test, and Development Commands

No application manifest or automated build exists yet. Add commands to the relevant README when scaffolding each service. Once manifests exist, the expected root-level workflow is:

```bash
npm --prefix frontend install
npm --prefix frontend run dev
python -m venv backend/.venv
python -m pip install -r backend/requirements.txt
python -m uvicorn app.main:app --reload --app-dir backend
python -m pytest backend/tests
```

Before committing documentation changes, run `git diff --check`. Keep installs reproducible with lockfiles or pinned requirements.

## Coding Style & Naming Conventions

Use 2-space indentation for TypeScript/JSON and 4 spaces for Python. Name React components in `PascalCase`, TypeScript functions in `camelCase`, and Python modules/functions in `snake_case`. Prefer small modules organized by responsibility, such as `backend/app/retrieval/chunker.py`. Configure ESLint/Prettier for the frontend and Ruff for Python when those projects are initialized; commit their configuration with the first code change.

## Testing Guidelines

Use `pytest` for backend logic and the Next.js scaffold's test runner for frontend code. Name Python tests `test_<behavior>.py` and frontend tests `*.test.ts(x)`. Cover chunking, metadata preservation, retrieval ranking, citation accuracy, API errors, and UI loading/error states. Mock external LLM and crawling calls; tests must not depend on paid APIs or mutable live pages.

## Commit & Pull Request Guidelines

Git history is not available in the current checkout, so use Conventional Commits: `feat: add citation metadata` or `docs: revise RAG architecture`. Keep commits focused. Pull requests should explain the user-visible change, list verification performed, link the relevant issue, and include screenshots for UI or presentation changes. Call out schema, prompt, data-source, or environment-variable changes explicitly.

## Security & Data Quality

Store API keys in untracked `.env` files and provide sanitized `.env.example` templates. Ingest only approved official department sources, retain canonical source URLs and retrieval timestamps, and never present uncited generated claims as official guidance.
