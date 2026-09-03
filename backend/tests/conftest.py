"""Separate pure unit tests from tests that need live infrastructure.

A clean clone has no PostgreSQL, Qdrant or MinIO running. Without this,
twenty database-backed tests fail with connection errors and the suite looks
broken rather than incomplete. Marked tests skip when their dependency is
unreachable, and run normally in CI where the services exist.

Set RUN_INTEGRATION=1 to turn a missing dependency back into a failure, which
is what CI wants: a service that should be up but is not must not pass silently.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlsplit

import pytest

# Modules whose tests reach PostgreSQL. Everything ending in `_integration`
# qualifies by name; these additionally do, without following that convention.
_DATABASE_BACKED_MODULES = frozenset(
    {
        "test_admin_control_plane",
        "test_chat_integration",
        "test_citizen_intake",
        "test_cookie_auth_integration",
    }
)

# Starting the FastAPI lifespan boots the durable job worker, which claims
# against PostgreSQL on its first poll.
_LIFESPAN_TESTS = frozenset({"test_application_lifespan_owns_one_service_and_closes_it"})


def _tcp_reachable(host: str, port: int, timeout: float = 0.75) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _database_endpoint() -> tuple[str, int]:
    """Resolve the configured database host and port without importing settings.

    conftest is imported before any test touches app configuration, and a
    malformed DATABASE_URL should not turn collection into an error here.
    """
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://legal_rag:legal_rag_dev_only@localhost:5432/legal_rag",
    )
    parts = urlsplit(url)
    try:
        port = parts.port or 5432
    except ValueError:
        port = 5432
    return parts.hostname or "localhost", port


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: requires live PostgreSQL (and, for some tests, Qdrant or MinIO)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    del config
    for item in items:
        module = item.module.__name__.rsplit(".", 1)[-1] if item.module else ""
        needs_database = (
            module.endswith("_integration")
            or module in _DATABASE_BACKED_MODULES
            or item.name in _LIFESPAN_TESTS
        )
        if needs_database:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def _require_database(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("integration") is None:
        return
    host, port = _database_endpoint()
    if _tcp_reachable(host, port):
        return
    if os.environ.get("RUN_INTEGRATION") == "1":
        pytest.fail(
            f"RUN_INTEGRATION=1 but PostgreSQL is unreachable at {host}:{port}. "
            "Start the compose stack before running the integration suite."
        )
    pytest.skip(
        f"PostgreSQL unreachable at {host}:{port}; "
        "start docker/docker-compose.yml or set RUN_INTEGRATION=1 to fail instead"
    )
