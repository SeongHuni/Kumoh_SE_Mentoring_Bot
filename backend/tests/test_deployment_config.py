import re

import pytest
from backend.app.config import REPOSITORY_ROOT

COMPOSE_PATH = REPOSITORY_ROOT / "compose.yaml"
DOCKERFILE_PATH = REPOSITORY_ROOT / "frontend" / "Dockerfile"
SERVICE_HEADER = re.compile(
    r'''(?m)^  (?P<raw_name>[A-Za-z0-9_-]+|"(?:\\.|[^"\\])*"|'(?:''|[^'])*'):[ \t]*\r?$'''
)
DOCKERFILE_STAGE = re.compile(r"(?im)^FROM[ \t]+.*[ \t]+AS[ \t]+[A-Za-z0-9_-]+[ \t]*$")
DOCKERFILE_BUILD = re.compile(r"(?m)^RUN npm run lint && npm run build[ \t]*$")
DOCKERFILE_URL_INSTRUCTION = re.compile(
    r"^(?:ARG|ENV)[ \t]+NEXT_PUBLIC_API_URL(?:[ \t]+.*|=.*)$"
)
EXPECTED_DOCKERFILE_URL_INSTRUCTIONS = (
    "ARG NEXT_PUBLIC_API_URL=http://localhost:8000",
    "ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL",
)
BACKEND_HEALTHCHECK = (
    """test: ["CMD", "python", "-c", "import urllib.request; """
    """urllib.request.urlopen('http://localhost:8000/api/live', timeout=3)"]"""
)
FRONTEND_HEALTHCHECK = (
    """test: ["CMD", "node", "-e", "fetch('http://localhost:3000').then("""
    """(response) => process.exit(response.ok ? 0 : 1)).catch(() => process.exit(1))"]"""
)


def compose_text() -> str:
    return COMPOSE_PATH.read_text(encoding="utf-8")


def dockerfile_text() -> str:
    return DOCKERFILE_PATH.read_text(encoding="utf-8")


def strip_yaml_comments(text: str) -> str:
    cleaned_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        newline = ""
        content = line
        if line.endswith("\r\n"):
            content, newline = line[:-2], "\r\n"
        elif line.endswith(("\n", "\r")):
            content, newline = line[:-1], line[-1]

        quote: str | None = None
        escaped = False
        comment_at: int | None = None
        index = 0
        while index < len(content):
            character = content[index]
            if quote == '"':
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quote = None
            elif quote == "'":
                if character == "'":
                    if index + 1 < len(content) and content[index + 1] == "'":
                        index += 1
                    else:
                        quote = None
            elif character in {'"', "'"}:
                quote = character
            elif character == "#" and (index == 0 or content[index - 1].isspace()):
                comment_at = index
                break
            index += 1

        if comment_at is not None:
            content = content[:comment_at].rstrip()
        cleaned_lines.append(content + newline)
    return "".join(cleaned_lines)


def _service_name(raw_name: str) -> str:
    if raw_name.startswith('"'):
        return raw_name[1:-1]
    if raw_name.startswith("'"):
        return raw_name[1:-1].replace("''", "'")
    return raw_name


def active_service_block(compose: str, service_name: str) -> str:
    active_compose = strip_yaml_comments(compose)
    headers = list(SERVICE_HEADER.finditer(active_compose))
    matches = [
        header
        for header in headers
        if _service_name(header.group("raw_name")) == service_name
    ]
    assert len(matches) == 1, (
        f"compose.yaml must contain exactly one active {service_name} service header; "
        f"found {len(matches)}"
    )

    service_header = matches[0]
    next_header = next(
        (header for header in headers if header.start() > service_header.start()),
        None,
    )
    end = next_header.start() if next_header else len(active_compose)
    return active_compose[service_header.start() : end]


def service_block(service_name: str) -> str:
    return active_service_block(compose_text(), service_name)


def assert_contract(block: str, contract: str, message: str) -> None:
    assert contract in block, message


def dockerfile_builder_before_build(dockerfile: str) -> str:
    active_dockerfile = "\n".join(
        line for line in dockerfile.splitlines() if not line.lstrip().startswith("#")
    )
    stages = list(DOCKERFILE_STAGE.finditer(active_dockerfile))
    builder_stages = [
        stage
        for stage in stages
        if re.search(r"(?i)[ \t]+AS[ \t]+builder[ \t]*$", stage.group())
    ]
    assert len(builder_stages) == 1, "frontend Dockerfile must contain exactly one builder stage"

    builder_stage = builder_stages[0]
    next_stage = next(
        (stage for stage in stages if stage.start() > builder_stage.start()),
        None,
    )
    stage_end = next_stage.start() if next_stage else len(active_dockerfile)
    builder = active_dockerfile[builder_stage.start() : stage_end]
    build_commands = list(DOCKERFILE_BUILD.finditer(builder))
    assert len(build_commands) == 1, (
        "frontend builder must contain exactly one npm build command"
    )
    return builder[: build_commands[0].start()]


def dockerfile_url_instructions(before_build: str) -> list[str]:
    return [
        line.strip()
        for line in before_build.splitlines()
        if DOCKERFILE_URL_INSTRUCTION.fullmatch(line.strip())
    ]


def assert_dockerfile_url_contract(dockerfile: str) -> None:
    instructions = dockerfile_url_instructions(dockerfile_builder_before_build(dockerfile))
    assert instructions == list(EXPECTED_DOCKERFILE_URL_INSTRUCTIONS), (
        "builder-before-build must contain only the canonical NEXT_PUBLIC_API_URL ARG/ENV chain"
    )


def assert_frontend_compose_api_url_contract(frontend: str) -> None:
    assert re.search(
        r"(?m)^[ \t]+NEXT_PUBLIC_API_URL:[ \t]*(?:"
        r"\$\{NEXT_PUBLIC_API_URL:-http://localhost:8000\}|"
        r'"\$\{NEXT_PUBLIC_API_URL:-http://localhost:8000\}")[ \t]*$',
        frontend,
    ), "frontend build arg must allow unquoted or double-quoted Compose interpolation"


def test_frontend_api_url_reaches_builder_before_build() -> None:
    frontend = service_block("frontend")
    assert_frontend_compose_api_url_contract(frontend)
    assert_dockerfile_url_contract(dockerfile_text())

    double_quoted = frontend.replace(
        "NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}",
        'NEXT_PUBLIC_API_URL: "${NEXT_PUBLIC_API_URL:-http://localhost:8000}"',
    )
    assert_frontend_compose_api_url_contract(double_quoted)

    single_quoted = frontend.replace(
        "NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}",
        "NEXT_PUBLIC_API_URL: '${NEXT_PUBLIC_API_URL:-http://localhost:8000}'",
    )
    with pytest.raises(AssertionError, match="unquoted or double-quoted"):
        assert_frontend_compose_api_url_contract(single_quoted)

    commented_override = dockerfile_text().replace(
        "ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL\n",
        "# ENV NEXT_PUBLIC_API_URL=http://localhost:8000\n"
        "ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL\n",
        1,
    )
    assert_dockerfile_url_contract(commented_override)

    builder_override = dockerfile_text().replace(
        "RUN npm run lint && npm run build",
        "ENV NEXT_PUBLIC_API_URL=http://localhost:8000\n"
        "RUN npm run lint && npm run build",
        1,
    )
    with pytest.raises(AssertionError, match="canonical NEXT_PUBLIC_API_URL"):
        assert_dockerfile_url_contract(builder_override)

    runner_override = dockerfile_text().replace(
        "FROM node:22-alpine AS runner",
        "FROM node:22-alpine AS runner\n"
        "ENV NEXT_PUBLIC_API_URL=http://localhost:8000",
        1,
    )
    assert_dockerfile_url_contract(runner_override)


def test_backend_healthcheck_targets_process_liveness_endpoint() -> None:
    assert_contract(
        service_block("backend"),
        BACKEND_HEALTHCHECK,
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
        FRONTEND_HEALTHCHECK,
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


def test_yaml_scanner_removes_inline_comments_without_touching_quoted_hashes() -> None:
    sample = r'''services:
  backend:
    healthcheck:
      test: ["CMD", "false"] # test: ["CMD", "python", "-c"]
      double: "keep # inside double quotes"
      escaped: "keep \" # inside escaped quote" # actual comment
      single: 'keep # inside single quotes'
'''

    backend = active_service_block(sample, "backend")

    assert 'test: ["CMD", "false"]' in backend
    assert '"python"' not in backend
    assert 'double: "keep # inside double quotes"' in backend
    assert r'escaped: "keep \" # inside escaped quote"' in backend
    assert "# actual comment" not in backend
    assert "single: 'keep # inside single quotes'" in backend


def test_service_block_unquotes_headers_and_stops_before_quoted_services() -> None:
    sample = """services:
  frontend:
    healthcheck:
      test: frontend-root
  "telemetry":
    healthcheck:
      test: telemetry-only
  'metrics':
    healthcheck:
      test: metrics-only
"""

    frontend = active_service_block(sample, "frontend")

    assert "frontend-root" in frontend
    assert "telemetry-only" not in frontend
    assert "metrics-only" not in frontend
    assert "telemetry-only" in active_service_block(sample, "telemetry")
    assert "metrics-only" in active_service_block(sample, "metrics")
    with pytest.raises(AssertionError, match="exactly one"):
        active_service_block(sample.replace('  "telemetry":', "  frontend:"), "frontend")
