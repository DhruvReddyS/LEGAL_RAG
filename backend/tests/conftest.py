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

# The suite commits what it writes, claims the oldest queued job of any user
# and leaves accounts behind, so it must never share a database with anything
# that matters. It runs against its own throwaway stack, started by
# scripts/run_backend_tests.sh. These defaults point at that stack rather than
# at the .env values, because env vars beat .env and a developer's .env names
# the live services. A database that is not named *_test is refused outright.
_TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://legal_rag:legal_rag_dev_only@127.0.0.1:55433/legal_rag_test",
)
if not urlsplit(_TEST_DATABASE_URL).path.rstrip("/").endswith("_test"):
    raise pytest.UsageError(
        "Refusing to run: TEST_DATABASE_URL must name a database ending in _test."
    )
os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
os.environ["JOB_WORKER_ENABLED"] = "false"
os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:56333")
os.environ.setdefault("S3_ENDPOINT_URL", "http://127.0.0.1:59000")
os.environ.setdefault("S3_PUBLIC_ENDPOINT_URL", "http://127.0.0.1:59000")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test-secret-key")

# Modules whose tests reach PostgreSQL. Everything ending in `_integration`
# qualifies by name; these additionally do, without following that convention.
_DATABASE_BACKED_MODULES = frozenset(
    {
        "test_admin_control_plane",
        "test_chat_integration",
        "test_citizen_intake",
        "test_cookie_auth_integration",
        # Named without the _integration suffix, so it was never gated and
        # failed with a connection error instead of skipping when Postgres is
        # down.
        "test_admin_case_scope",
        # Both provision users, so they failed instead of skipping as well.
        "test_chat_message_order_is_stable",
        "test_queue_position_is_visible",
    }
)

# Modules that put bytes in MinIO. These need object storage on top of the
# database, and S3_ENDPOINT_URL usually names a host only the compose network
# can resolve.
_OBJECT_STORAGE_MODULES = frozenset(
    {
        "test_storage_integration",
        "test_case_document_indexing_integration",
        "test_cross_tenant_integration",
    }
)

# Modules that drive DurableJobWorker directly. claim_next_job is unscoped by
# design -- any worker takes the oldest queued job of a supported type -- so
# these tests are only meaningful when no other worker polls the same database.
_JOB_WORKER_MODULES = frozenset(
    {"test_jobs_integration", "test_queue_position_is_visible"}
)

# Where a developer's own backend usually listens. If something is serving
# there it is almost certainly the API, whose durable worker polls this same
# database every JOB_POLL_INTERVAL_MS.
_LOCAL_BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))

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


def _object_storage_endpoint() -> tuple[str, int]:
    """Resolve the configured object-storage host and port.

    S3_ENDPOINT_URL carries the name the *backend container* uses to reach
    MinIO, which does not resolve on a developer's machine. A suite run
    natively should say so and skip, rather than fail with a name-resolution
    error that looks like a broken test.
    """
    url = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000")
    parts = urlsplit(url)
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        port = 9000
    return parts.hostname or "localhost", port


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: requires live PostgreSQL (and, for some tests, Qdrant or MinIO)",
    )
    config.addinivalue_line(
        "markers",
        "object_storage: requires MinIO reachable at S3_ENDPOINT_URL",
    )
    config.addinivalue_line(
        "markers",
        "redteam: adversarial cross-tenant checks; reported as their own CI group",
    )
    config.addinivalue_line(
        "markers",
        "sole_job_worker: requires that no other job worker polls this database",
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
        )
        if needs_database:
            item.add_marker(pytest.mark.integration)
        if module in _OBJECT_STORAGE_MODULES:
            item.add_marker(pytest.mark.object_storage)
        if module in _JOB_WORKER_MODULES:
            item.add_marker(pytest.mark.sole_job_worker)


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


@pytest.fixture(autouse=True)
def _require_object_storage(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("object_storage") is None:
        return
    host, port = _object_storage_endpoint()
    if _tcp_reachable(host, port):
        return
    if os.environ.get("RUN_INTEGRATION") == "1":
        pytest.fail(
            f"RUN_INTEGRATION=1 but object storage is unreachable at {host}:{port}. "
            "Run the suite inside the compose network, or point S3_ENDPOINT_URL at "
            "the host-published address (S3_PUBLIC_ENDPOINT_URL)."
        )
    pytest.skip(
        f"Object storage unreachable at {host}:{port}; "
        "S3_ENDPOINT_URL names the compose-internal host, which does not "
        "resolve outside the container network"
    )


@pytest.fixture(autouse=True)
def _require_sole_job_worker(request: pytest.FixtureRequest) -> None:
    """Refuse to run worker tests while another worker competes for jobs.

    claim_next_job takes the oldest queued job of a supported type for any
    user -- the contract that makes it safe to run several workers in
    production. It also means a backend running on this machine claims the job
    a test just enqueued, within one poll interval, and then *executes* it
    through the real Deep pipeline against Ollama.

    The test then fails on `assert claimed == job_id` with no hint that another
    process was involved, and only sometimes, because it is a race.
    """
    if request.node.get_closest_marker("sole_job_worker") is None:
        return
    if not _tcp_reachable("127.0.0.1", _LOCAL_BACKEND_PORT):
        request.getfixturevalue("_swept_stale_jobs")
        return
    message = (
        f"a service is listening on 127.0.0.1:{_LOCAL_BACKEND_PORT}; its durable "
        "job worker polls this same database and will claim and execute the jobs "
        "these tests enqueue. Stop the local backend, run with "
        "JOB_WORKER_ENABLED=false, or point DATABASE_URL at another database."
    )
    if os.environ.get("RUN_INTEGRATION") == "1":
        pytest.fail(f"RUN_INTEGRATION=1 but {message}")
    pytest.skip(message)


@pytest.fixture(scope="session")
def _swept_stale_jobs():
    """Remove jobs an earlier interrupted run left behind.

    The durable worker claims any QUEUED job, by design. In tests that means
    one orphan is picked up instead of the job the test just created, and the
    jobs suite fails for a reason unrelated to the change under test.

    Requested only by the worker tests: as a session-wide autouse fixture this
    needed a working database for every test, so one unreachable login turned
    the pure unit tests into 358 setup errors. It uses its own engine because
    asyncio.run() owns a private loop, and pooled asyncpg connections bind to
    the loop that opened them.
    """
    import asyncio
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.models import Job
    from app.models.enums import JobStatus

    async def sweep() -> None:
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        # Only jobs old enough that no run could still be working on them.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        try:
            async with AsyncSession(engine) as session:
                await session.execute(
                    delete(Job).where(
                        Job.status.in_((JobStatus.QUEUED, JobStatus.RUNNING)),
                        Job.created_at < cutoff,
                    )
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(sweep())
