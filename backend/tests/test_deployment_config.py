import re

import pytest
from backend.app.config import REPOSITORY_ROOT

COMPOSE_PATH = REPOSITORY_ROOT / "compose.yaml"
DOCKERFILE_PATH = REPOSITORY_ROOT / "frontend" / "Dockerfile"
SERVICE_HEADER = re.compile(
    r"(?m)^  (?P<name>[A-Za-z0-9_-]+):[ \t]*(?:#.*)?\r?$"
)


def compose_text() -> str:
    return COMPOSE_PATH.read_text(encoding="utf-8")


def dockerfile_text() -> str:
    return DOCKERFILE_PATH.read_text(encoding="utf-8")


def active_service_block(compose: str, service_name: str) -> str:
    headers = list(SERVICE_HEADER.finditer(compose))
    matches = [header for header in headers if header.group("name") == service_name]
    assert len(matches) == 1, (
        f"compose.yaml must contain exactly one active {service_name} service header; "
        f"found {len(matches)}"
    )

    service_header = matches[0]
    next_header = next(
        (header for header in headers if header.start() > service_header.start()),
        None,
    )
    end = next_header.start() if next_header else len(compose)
    block = compose[service_header.start() : end]
    return "\n".join(
        line for line in block.splitlines() if not line.lstrip().startswith("#")
    )


def service_block(service_name: str) -> str:
    return active_service_block(compose_text(), service_name)


def assert_contract(block: str, contract: str, message: str) -> None:
    assert contract in block, message


def test_frontend_build_receives_configurable_api_url() -> None:
    assert_contract(
        service_block("frontend"),
        "NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}",
        "frontend build arg must use NEXT_PUBLIC_API_URL with the local default",
    )


def test_frontend_api_url_reaches_builder_before_build() -> None:
    frontend = service_block("frontend")
    assert re.search(
        r"(?m)^[ \t]+NEXT_PUBLIC_API_URL:[ \t]*"
        r'(?:\$\{NEXT_PUBLIC_API_URL:-http://localhost:8000\}|"'
        r'\$\{NEXT_PUBLIC_API_URL:-http://localhost:8000\}")[ \t]*$',
        frontend,
    ), "frontend build arg must allow unquoted or double-quoted Compose interpolation"

    dockerfile = dockerfile_text()
    builder_header = re.search(r"(?m)^FROM .* AS builder[ \t]*$", dockerfile)
    assert builder_header, "frontend Dockerfile must define a builder stage"
    runner_header = re.search(r"(?m)^FROM .* AS runner[ \t]*$", dockerfile)
    builder_end = runner_header.start() if runner_header else len(dockerfile)
    builder = dockerfile[builder_header.start() : builder_end]

    build_command = re.search(
        r"(?m)^RUN npm run lint && npm run build[ \t]*$",
        builder,
    )
    assert build_command, "frontend builder must contain the build command"
    before_build = builder[: build_command.start()]
    assert re.search(
        r"(?m)^ARG NEXT_PUBLIC_API_URL=http://localhost:8000[ \t]*$",
        before_build,
    ), "frontend builder must declare NEXT_PUBLIC_API_URL before build"
    assert re.search(
        r"(?m)^ENV NEXT_PUBLIC_API_URL=\$NEXT_PUBLIC_API_URL[ \t]*$",
        before_build,
    ), "frontend builder must export NEXT_PUBLIC_API_URL before build"


def test_backend_healthcheck_targets_process_liveness_endpoint() -> None:
    assert_contract(
        service_block("backend"),
        (
            'test: ["CMD", "python", "-c", "import urllib.request; '
            "urllib.request.urlopen('http://localhost:8000/api/live', timeout=3)\"]"
        ),
        "backend healthcheck must probe /api/live with urllib.request",
    )
    assert_contract(
        service_block("backend"),
        "interval: 10s\n      timeout: 5s\n      retries: 5\n      start_period: 10s",
        "backend healthcheck must use the standard retry timing",
    )


def test_frontend_waits_for_healthy_backend() -> None:
    assert_contract(
        service_block("frontend"),
        "depends_on:\n      backend:\n        condition: service_healthy",
        "frontend must wait for the backend service healthcheck",
    )


def test_frontend_healthcheck_uses_node_fetch_for_process_liveness() -> None:
    assert_contract(
        service_block("frontend"),
        (
            'test: ["CMD", "node", "-e", "fetch(\'http://localhost:3000\').then('
            "(response) => process.exit(response.ok ? 0 : 1)).catch(() => process.exit(1))\"]"
        ),
        "frontend healthcheck must use Node fetch against the process root",
    )
    assert_contract(
        service_block("frontend"),
        "interval: 10s\n      timeout: 5s\n      retries: 5\n      start_period: 10s",
        "frontend healthcheck must use the standard retry timing",
    )


def test_compose_does_not_gate_startup_on_rag_readiness() -> None:
    backend = service_block("backend")
    frontend = service_block("frontend")
    assert "/api/health" not in backend + frontend, (
        "compose startup checks must use process liveness /api/live, not RAG readiness /api/health"
    )
    assert "/api/live" in backend, "backend process healthcheck must use /api/live"


def test_active_service_block_ignores_comments_other_services_and_duplicates() -> None:
    sample = """services:
  backend:
    # frontend-only test: node fetch http://localhost:3000
    healthcheck:
      test: backend-live
  frontend:
    healthcheck:
      test: frontend-only
"""

    backend = active_service_block(sample, "backend")

    assert "frontend-only" not in backend
    assert "frontend-only test" not in backend
    with pytest.raises(AssertionError, match="exactly one"):
        active_service_block(sample.replace("  frontend:", "  backend:"), "backend")
