"""Audit 03 F-09: a job stream must not pin a database connection or go uncapped."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.core.security import create_access_token
from app.models import Job, JobEvent, User, UserSession
from app.models.enums import JobStatus, JobType
from app.routers.jobs import stream_job_events
from app.services.job_streams import JobStreamGate, StreamLimitReached, job_stream_gate
from main import app
from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _owner_with_job(status: JobStatus = JobStatus.RUNNING) -> tuple[dict, uuid.UUID]:
    body = await provision_test_user(
        name="Stream Owner", email=unique_email("stream"), password="Stream-Password-1234", role="citizen"
    )
    async with AsyncSessionLocal() as session:
        job = Job(
            user_id=uuid.UUID(body["user"]["id"]),
            type=JobType.DEEP_REVIEW,
            status=status,
            progress=10,
            idempotency_key=f"stream-{uuid.uuid4().hex}",
            payload={},
            max_attempts=3,
        )
        session.add(job)
        await session.flush()
        session.add(JobEvent(job_id=job.id, event_type="stage", stage="retrieving", progress=10, data={"label": "Searching"}))
        await session.commit()
        return body, job.id


class _Connected:
    def __init__(self, token: str) -> None:
        self.headers = {"authorization": f"Bearer {token}"}
        self.cookies: dict[str, str] = {}

    async def is_disconnected(self) -> bool:
        return False


def test_the_gate_counts_per_user_and_releases() -> None:
    gate = JobStreamGate()
    gate.acquire("a", limit=2)
    gate.acquire("a", limit=2)
    gate.acquire("b", limit=2)
    with pytest.raises(StreamLimitReached):
        gate.acquire("a", limit=2)
    gate.release("a")
    gate.acquire("a", limit=2)
    assert gate.open_count("a") == 2 and gate.open_count("b") == 1


async def test_a_finished_stream_says_so_and_releases_its_slot() -> None:
    body, job_id = await _owner_with_job(JobStatus.SUCCEEDED)
    user_key = body["user"]["id"]
    async with _client() as client:
        response = await client.get(
            f"/jobs/{job_id}/events", headers={"Authorization": f"Bearer {body['access_token']}"}
        )
    assert response.status_code == 200
    assert "event: stage" in response.text
    assert response.text.rstrip().endswith('data: {"reason":"finished"}')
    assert job_stream_gate.open_count(user_key) == 0


async def test_streams_beyond_the_cap_are_refused(monkeypatch) -> None:
    monkeypatch.setattr(settings, "job_streams_per_user", 1)
    body, job_id = await _owner_with_job()
    user_key = body["user"]["id"]
    job_stream_gate.acquire(user_key, limit=1)
    try:
        async with _client() as client:
            refused = await client.get(
                f"/jobs/{job_id}/events", headers={"Authorization": f"Bearer {body['access_token']}"}
            )
        assert refused.status_code == 429
        assert refused.headers["retry-after"] == "5"
    finally:
        job_stream_gate.release(user_key)


async def test_someone_elses_stream_takes_no_slot_and_is_refused() -> None:
    _, job_id = await _owner_with_job()
    stranger = await provision_test_user(
        name="Stranger", email=unique_email("stream-stranger"), password="Stream-Password-1234", role="citizen"
    )
    async with _client() as client:
        refused = await client.get(
            f"/jobs/{job_id}/events", headers={"Authorization": f"Bearer {stranger['access_token']}"}
        )
    assert refused.status_code == 404
    assert job_stream_gate.open_count(stranger["user"]["id"]) == 0


async def test_an_open_stream_holds_no_database_connection() -> None:
    body, job_id = await _owner_with_job()
    user_id = uuid.UUID(body["user"]["id"])
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        response = await stream_job_events(
            job_id,
            _Connected(body["access_token"]),  # type: ignore[arg-type]
            after=0,
            last_event_id=None,
            user=user,
            session=session,
        )
        assert not session.in_transaction()
        iterator = response.body_iterator
        first = await iterator.__anext__()
        assert "event: stage" in first
        # Between events, with the stream open and the job still running.
        assert engine.pool.checkedout() == 0
        await iterator.aclose()
    assert job_stream_gate.open_count(str(user_id)) == 0


async def test_revoking_the_device_ends_a_stream_already_open(monkeypatch) -> None:
    monkeypatch.setattr(settings, "job_stream_recheck_seconds", 1.0)
    body, job_id = await _owner_with_job()
    user_id = uuid.UUID(body["user"]["id"])
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        device = UserSession(
            user_id=user_id,
            label="Test device",
            expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )
        session.add(device)
        await session.commit()
        token = create_access_token(user, device.id)

        response = await stream_job_events(
            job_id, _Connected(token), after=0, last_event_id=None, user=user, session=session  # type: ignore[arg-type]
        )
    iterator = response.body_iterator
    assert "event: stage" in await iterator.__anext__()

    async with AsyncSessionLocal() as session:
        row = await session.get(UserSession, device.id)
        row.revoked_at = datetime.now(timezone.utc)
        await session.commit()

    collected = ""
    async for chunk in iterator:
        collected += chunk
    assert "session_ended" in collected
    assert job_stream_gate.open_count(str(user_id)) == 0
