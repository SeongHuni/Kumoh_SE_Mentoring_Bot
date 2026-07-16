# Repository Guidelines

## Project Structure & Canonical Documentation

- `frontend/`: Next.js 채팅 UI와 colocated Vitest 테스트.
- `backend/app/`: FastAPI, RAG orchestration, retrieval, citations, crawler 구현.
- `backend/scripts/`: 수집, 인덱싱, 평가, 데이터 감사 CLI.
- `backend/tests/`: pytest 단위·통합 테스트.
- `data/raw/posts.json`: 현재 canonical source snapshot; 생성 후보, 보고서, 인덱스는 추적하지 않는다.
- `docs/PROJECT_STATUS.md`: 현재 건수, 준비도, 위험, 남은 검증의 기준 문서.
- `docs/HANDOFF.md`: 다음 작업자의 시작 명령과 변경 금지선.
- `docs/RAG_ARCHITECTURE.md`: 안정적인 RAG 문서 목차와 불변 조건.
- `docs/rag/operations-evaluation.md`: 운영 명령과 평가 절차의 권위 있는 기준.
- `docs/superpowers/**` 및 `docs/reference/**`: 날짜가 있는 역사 자료이며 현재 운영 문서보다 우선하지 않는다.

현재 수치·준비도·위험은 `docs/PROJECT_STATUS.md`, 실행 명령은 `docs/rag/operations-evaluation.md`, 환경변수 기본값은 `.env.example`을 우선한다. README는 사용자 설치·실행 진입점이다.

## Build, Test, and Development Commands

설치와 기본 실행은 `README.md`, 전체 운영·평가 명령은 `docs/rag/operations-evaluation.md`를 따른다. Backend 개발 의존성은 `backend/requirements-dev.txt`에서 설치하고 frontend 의존성은 lockfile을 반영하는 `npm --prefix frontend ci`로 설치한다. 루트 품질 workflow는 `.github/workflows/quality.yml`이다.

```powershell
py -3 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
backend/.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests --cov=backend.app --cov=backend.scripts --cov-config=backend/pyproject.toml --cov-report=term-missing
backend/.venv/Scripts/python.exe -m ruff check backend
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

수집은 허용된 기본 경로의 `backend/.venv/Scripts/python.exe -m backend.scripts.crawl --kumoh-limit 50 --seboard-limit 0`을 사용한다. SE limit을 양수로 바꾸려면 실제 운영자 서면 허가 또는 승인된 공식 API가 먼저 문서화되어야 하며, `--seboard-permission-confirmed`는 그 확인을 CLI에 기록할 뿐 권한을 대신하지 않는다.

## Coding, Testing, and Security

TypeScript/JSON은 2칸, Python은 4칸 들여쓰기를 사용한다. React component는 `PascalCase`, TypeScript 함수는 `camelCase`, Python 함수와 모듈은 `snake_case`로 이름 짓는다. 동작을 바꾸기 전에는 실패하는 테스트를 먼저 추가하고, 유료 API와 변경 가능한 live page는 mock한다. Backend는 pytest, frontend는 colocated Vitest 테스트를 사용하며, 청킹·metadata 보존·retrieval ranking·citation accuracy·API 오류·UI loading/error 상태를 회귀 범위로 유지한다.

커밋 전 `git diff --check`를 실행한다. `.env`, API key·password·bearer token 같은 secrets, vector index, local database, 생성 보고서, coverage/build output은 커밋하지 않는다. 승인된 공식 학과 source의 canonical URL과 retrieval timestamp를 보존하고, 출처 없는 생성 주장을 공식 안내처럼 제시하지 않는다. SE collection은 운영자 서면 허가 또는 승인된 공식 API가 문서화되기 전까지 비활성 상태를 유지한다.

## Commits and Pull Requests

변경 범위가 명확한 focused Conventional Commit을 사용한다(예: `docs: align setup and contributor guidance`). Pull request에는 사용자에게 보이는 변경, 실행한 검증과 결과, 관련 issue, 그리고 schema·prompt·data-source·dependency·environment-variable 변경을 명시한다. UI나 presentation이 실질적으로 바뀌면 screenshot을 첨부한다.
