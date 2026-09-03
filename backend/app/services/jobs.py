from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobEvent
from app.models.enums import JobStatus, JobType


TERMINAL_JOB_STATUSES = {
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
}


def append_job_event(
    session: AsyncSession,
    job: Job,
    *,
    event_type: str,
    stage: str | None = None,
    data: dict[str, Any] | None = None,
) -> JobEvent:
    event = JobEvent(
        job_id=job.id,
        event_type=event_type[:64],
        stage=stage[:64] if stage else None,
        progress=job.progress,
        data=data or {},
    )
    session.add(event)
    return event


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def mark_job_running(job: Job) -> None:
    if job.status is not JobStatus.QUEUED:
        raise ValueError(f"cannot run a {job.status.value} job")
    job.status = JobStatus.RUNNING
    job.attempt_count += 1
    job.started_at = utc_now()
    job.completed_at = None
    job.error_code = None
    job.error_message = None


def update_job_progress(job: Job, progress: int) -> None:
    if job.status is not JobStatus.RUNNING:
        raise ValueError("progress can only change while a job is running")
    if progress < job.progress or not 0 <= progress <= 99:
        raise ValueError("running job progress must be monotonic and between 0 and 99")
    job.progress = progress


def mark_job_succeeded(job: Job, result: dict[str, Any]) -> None:
    if job.status is not JobStatus.RUNNING:
        raise ValueError(f"cannot succeed a {job.status.value} job")
    job.status = JobStatus.SUCCEEDED
    job.progress = 100
    job.result = result
    job.completed_at = utc_now()


def record_job_failure(job: Job, *, code: str, message: str) -> bool:
    """Record an attempt failure and return whether the job will retry."""

    if job.status is not JobStatus.RUNNING:
        raise ValueError(f"cannot fail a {job.status.value} job")
    job.error_code = code[:64]
    job.error_message = message[:500]
    if job.cancel_requested:
        job.status = JobStatus.CANCELLED
        job.completed_at = utc_now()
        return False
    if job.attempt_count < job.max_attempts:
        job.status = JobStatus.QUEUED
        job.progress = 0
        job.started_at = None
        return True
    job.status = JobStatus.FAILED
    job.completed_at = utc_now()
    return False


def request_job_cancellation(job: Job) -> None:
    if job.status is JobStatus.CANCELLED:
        return
    if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED}:
        raise ValueError(f"cannot cancel a {job.status.value} job")
    job.cancel_requested = True
    if job.status is JobStatus.QUEUED:
        job.status = JobStatus.CANCELLED
        job.completed_at = utc_now()


def mark_job_cancelled(job: Job) -> None:
    if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
        raise ValueError(f"cannot cancel a {job.status.value} job")
    job.status = JobStatus.CANCELLED
    job.cancel_requested = True
    job.completed_at = utc_now()


async def claim_next_job(
    session: AsyncSession,
    *,
    supported_types: Iterable[JobType],
) -> Job | None:
    job = await session.scalar(
        select(Job)
        .where(
            Job.status == JobStatus.QUEUED,
            Job.type.in_(tuple(supported_types)),
        )
        .order_by(Job.created_at, Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    if job.cancel_requested:
        request_job_cancellation(job)
        return job
    mark_job_running(job)
    return job


async def recover_interrupted_jobs(session: AsyncSession) -> int:
    jobs = list(
        (
            await session.scalars(
                select(Job).where(Job.status == JobStatus.RUNNING).with_for_update()
            )
        ).all()
    )
    for job in jobs:
        if job.cancel_requested:
            mark_job_cancelled(job)
        elif job.attempt_count >= job.max_attempts:
            job.status = JobStatus.FAILED
            job.error_code = "worker_interrupted"
            job.error_message = "Worker stopped before the job completed"
            job.completed_at = utc_now()
        else:
            job.status = JobStatus.QUEUED
            job.progress = 0
            job.started_at = None
            job.error_code = "worker_interrupted"
            job.error_message = "Worker stopped; job returned to the queue"
    return len(jobs)


def owned_jobs_query(user_id: Any, *, include_all: bool) -> Select[tuple[Job]]:
    query = select(Job)
    if not include_all:
        query = query.where(Job.user_id == user_id)
    return query
