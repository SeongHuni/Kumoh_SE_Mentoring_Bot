from backend.app.config import REPOSITORY_ROOT

COMPOSE_PATH = REPOSITORY_ROOT / "compose.yaml"


def compose_text() -> str:
    return COMPOSE_PATH.read_text(encoding="utf-8")


def assert_contract(contract: str, message: str) -> None:
    assert contract in compose_text(), message


def test_frontend_build_receives_configurable_api_url() -> None:
    assert_contract(
        "NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}",
        "frontend build arg must use NEXT_PUBLIC_API_URL with the local default",
    )


def test_backend_healthcheck_targets_process_liveness_endpoint() -> None:
    assert_contract(
        (
            'test: ["CMD", "python", "-c", "import urllib.request; '
            "urllib.request.urlopen('http://localhost:8000/api/live', timeout=3)\"]"
        ),
        "backend healthcheck must probe /api/live with urllib.request",
    )
    assert_contract(
        "interval: 10s\n      timeout: 5s\n      retries: 5\n      start_period: 10s",
        "backend healthcheck must use the standard retry timing",
    )


def test_frontend_waits_for_healthy_backend() -> None:
    assert_contract(
        "depends_on:\n      backend:\n        condition: service_healthy",
        "frontend must wait for the backend service healthcheck",
    )


def test_frontend_healthcheck_uses_node_fetch_for_process_liveness() -> None:
    assert_contract(
        (
            'test: ["CMD", "node", "-e", "fetch(\'http://localhost:3000\').then('
            "(response) => process.exit(response.ok ? 0 : 1)).catch(() => process.exit(1))\"]"
        ),
        "frontend healthcheck must use Node fetch against the process root",
    )
    assert_contract(
        "interval: 10s\n      timeout: 5s\n      retries: 5\n      start_period: 10s",
        "frontend healthcheck must use the standard retry timing",
    )


def test_compose_does_not_gate_startup_on_rag_readiness() -> None:
    assert "/api/health" not in compose_text(), (
        "compose startup checks must use process liveness /api/live, not RAG readiness /api/health"
    )
