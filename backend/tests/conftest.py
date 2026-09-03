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


# Settings resolve env vars ahead of the .env file, so these must be set before
# anything imports app configuration - which happens on the first `from main
# import app` inside a test.
#
# Without this the suite silently inherits the developer's own .env. A local
# .env narrows TRUSTED_HOSTS to real hosts, which is correct for a deployment
# and rejects the ASGI transport's "test" host with 400 on every request,
# producing dozens of failures that look like application bugs. CI has no .env
# and so never saw it.
# Only the two values the ASGI transport forces. Everything else is left to
# the application defaults, so a test never asserts against a value this file
# invented - and in particular COOKIE_SECURE stays unset, since several tests
# construct Settings directly and assert its environment-derived behaviour.
os.environ.setdefault("APP_ENV", "development")
os.environ["TRUSTED_HOSTS"] = "localhost,127.0.0.1,test,testserver"
os.environ["CORS_ORIGINS"] = (
    "http://test,http://localhost:3000,http://127.0.0.1:3000,"
    "http://tauri.localhost,tauri://localhost"
)

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


@pytest.fixture(scope="session", autouse=True)
def _clear_stale_queued_jobs():
    """Remove jobs left behind by an earlier interrupted run.

    The durable worker claims any QUEUED job, by design - that is what makes it
    safe to run several. In tests it means one orphan from a run that failed
    part-way is picked up instead of the job the test just created, and the
    jobs suite then fails for a reason that has nothing to do with the change
    under test. CI gets a fresh database and never sees this; a developer
    re-running locally sees it every time.

    Only jobs that predate this session are removed, so nothing a running test
    created is touched.
    """
    host, port = _database_endpoint()
    if not _tcp_reachable(host, port):
        yield
        return

    import asyncio
    from datetime import datetime, timedelta, timezone

    async def sweep() -> None:
        from sqlalchemy import delete

        from app.core.database import AsyncSessionLocal
        from app.models import Job
        from app.models.enums import JobStatus

        from app.core.database import engine

        # Only jobs old enough that no run could still be working on them.
        # "Predates this session" was wrong: a developer with the app open
        # against the same database had a live Deep job deleted mid-flight, and
        # the browser then polled a job id that no longer existed.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(Job).where(
                        Job.status.in_((JobStatus.QUEUED, JobStatus.RUNNING)),
                        Job.created_at < cutoff,
                    )
                )
                await session.commit()
        finally:
            # asyncio.run() below owns a private event loop. Pooled asyncpg
            # connections bind to the loop that opened them, so leaving any
            # behind hands the session-scoped test loop a connection attached
            # to a loop that no longer exists.
            await engine.dispose()

    asyncio.run(sweep())
    yield
