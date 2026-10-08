"""A queued reader is told where they are, because they cannot be served sooner.

Generation is one slot and the worker is FIFO, so the second of two Deep jobs
waits for the first answer before anything happens for it -- measured at
38.4 s. Running jobs concurrently to fix that was measured and rejected: it
left the last user finishing at the same ~74 s while making the *first* asker
wait 81% longer, because two jobs in flight interleave on the generation
semaphore and turn FIFO into round-robin.

So the wait is irreducible on this host, and the honest thing is to name it.
These tests pin that a queued job reports its position and an estimate, that a
running or finished job reports neither, and that the estimate is built on a
measured constant rather than an average of recent runs.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.models import Job
from app.models.enums import JobStatus, JobType
from app.routers.jobs import DEEP_JOB_TYPICAL_SECONDS
from tests.helpers import provision_test_user


# `claim_next_job` is FIFO across the whole table, so a queued row left behind
# here is claimed by the next test that starts a worker -- and that test then
# runs somebody else's job and fails on what it gets back. Observed exactly
# once, as an intermittent failure in the durable-jobs integration test that
# passed in isolation and failed in the suite.
#
# Cleanup is a context manager rather than an autouse fixture: an async
# fixture is given a function-scoped event loop while these tests run on the
# session loop, and the asyncpg connection then belongs to the wrong one.


@asynccontextmanager
async def queued_jobs(user_id: uuid.UUID, count: int, *, status=JobStatus.QUEUED):
    """Create `count` jobs, hand back their ids, and remove them afterwards."""
    ids: list[uuid.UUID] = []
    async with AsyncSessionLocal() as session:
        for index in range(count):
            job = Job(
                user_id=user_id,
                type=JobType.DEEP_REVIEW,
                status=status,
                progress=0,
                idempotency_key=f"queue-test-{uuid.uuid4().hex}",
                payload={"query": f"question {index}", "role": "citizen"},
                max_attempts=3,
            )
            session.add(job)
            await session.flush()
            ids.append(job.id)
        await session.commit()
    try:
        yield ids
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Job).where(Job.id.in_(ids)))
            await session.commit()


async def _user_id() -> uuid.UUID:
    user = await provision_test_user(
        name="Queue User",
        email=f"queue-{uuid.uuid4().hex}@example.com",
        password="CorrectHorseBattery99!",
        role="citizen",
    )
    return uuid.UUID(str(user["user"]["id"]))


@pytest.mark.asyncio
async def test_the_estimate_rests_on_a_measured_constant_not_a_moving_average() -> None:
    """An average over recent jobs would track the host's temperature.

    The same prompt producing the same 597 tokens took 42.5 s on a warm
    laptop and 26.4 s on a cool one. An estimate built on that would halve
    between two refreshes; a citizen is better served by a stable
    over-estimate.
    """
    assert DEEP_JOB_TYPICAL_SECONDS >= 65, "below the measured Deep p50 of 65-72 s"
    assert DEEP_JOB_TYPICAL_SECONDS <= 150, "above the measured p95; that is not an estimate"


@pytest.mark.asyncio
async def test_position_counts_everything_claimable_ahead_of_the_job() -> None:
    """Including jobs that are already running, which the worker will not re-claim."""
    from app.models import User
    from app.routers.jobs import read_job

    user_id = await _user_id()
    async with queued_jobs(user_id, 2) as earlier, queued_jobs(user_id, 1) as mine:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            response = await read_job(mine[0], user=user, session=session)
        assert response.queue_position is not None
        assert response.queue_position >= len(earlier) + 1
        assert (
            response.estimated_wait_seconds
            == response.queue_position * DEEP_JOB_TYPICAL_SECONDS
        )


@pytest.mark.asyncio
async def test_a_job_that_is_not_queued_reports_no_position() -> None:
    """A running job's position would be a lie, and a finished one's noise."""
    from app.routers.jobs import read_job
    from app.models import User

    user_id = await _user_id()
    async with queued_jobs(user_id, 1, status=JobStatus.RUNNING) as running:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            response = await read_job(running[0], user=user, session=session)
    assert response.queue_position is None
    assert response.estimated_wait_seconds is None


@pytest.mark.asyncio
async def test_the_first_job_in_an_empty_queue_is_position_one() -> None:
    from app.routers.jobs import read_job
    from app.models import User

    # Deliberately not "cancel everything claimable so the queue is empty".
    # That was the first version of this test and it reached into rows this
    # module does not own, which is how a durable-jobs integration test
    # started failing intermittently. Position is asserted relative to what
    # is actually ahead instead.
    async with AsyncSessionLocal() as session:
        ahead = int(
            await session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
            )
            or 0
        )

    user_id = await _user_id()
    async with queued_jobs(user_id, 1) as only:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            response = await read_job(only[0], user=user, session=session)
        assert response.queue_position == ahead + 1
        assert response.estimated_wait_seconds == (ahead + 1) * DEEP_JOB_TYPICAL_SECONDS
