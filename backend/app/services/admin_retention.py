"""Retention periods, and a purge that only deletes what a dry run showed.

A purge consumes a dry run: same administrator, recent, the policy unchanged, and
the cutoffs fixed when the dry run was taken. So what a person reviewed is what
goes, and a period lowered between the preview and the click cannot widen it.

Every category defaults to keeping everything. Case material carries legal
obligations this system cannot judge, so nothing is deleted until someone sets a
period, and each period has a floor.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from qdrant_client import models
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.case_scope import collection_for_case_role
from app.models import AuditLog, Case, ChatMessage, ChatSession, Job, RevokedRefreshToken, StorageObject, User
from app.models.admin_tools import RetentionPolicy, RetentionRun
from app.models.enums import JobStatus
from app.services.storage import create_s3_client

logger = logging.getLogger("legal_rag.retention")

DRY_RUN_VALID_MINUTES = 15
PURGE_CONFIRMATION = "PURGE"
_TERMINAL_JOBS = (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)
_CLOSED_CASE_STATUSES = ("closed", "archived")


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    description: str
    minimum_days: int


CATEGORIES: tuple[Category, ...] = (
    Category(
        "chat_history",
        "Conversations",
        "Conversations not attached to a case, after their last message. Ratings on them go too.",
        7,
    ),
    Category(
        "job_records",
        "Background jobs",
        "Finished jobs and their results and events. Running and queued jobs are never touched.",
        7,
    ),
    Category(
        "audit_logs",
        "Audit log",
        "Audit rows older than this. Records of retention itself are kept.",
        365,
    ),
    Category(
        "closed_cases",
        "Closed cases",
        "Closed or archived cases opened longer ago than this: their documents, indexed "
        "passages, drafts and conversations, from every store.",
        365,
    ),
)
_BY_KEY = {category.key: category for category in CATEGORIES}


async def _policy_days(session: AsyncSession) -> dict[str, int | None]:
    rows = (await session.scalars(select(RetentionPolicy))).all()
    stored = {row.category: row.days for row in rows}
    return {category.key: stored.get(category.key) for category in CATEGORIES}


async def retention_state(session: AsyncSession) -> dict[str, Any]:
    days = await _policy_days(session)
    runs = (
        await session.execute(
            select(RetentionRun, User.name)
            .outerjoin(User, User.id == RetentionRun.requested_by)
            .order_by(RetentionRun.created_at.desc())
            .limit(20)
        )
    ).all()
    return {
        "categories": [
            {
                "key": category.key,
                "label": category.label,
                "description": category.description,
                "minimum_days": category.minimum_days,
                "days": days[category.key],
            }
            for category in CATEGORIES
        ],
        "runs": [
            {
                "id": str(run.id),
                "kind": run.kind,
                "dry_run_id": str(run.dry_run_id) if run.dry_run_id else None,
                "counts": run.counts,
                "requested_by": name,
                "created_at": run.created_at.isoformat(),
            }
            for run, name in runs
        ],
        "dry_run_valid_minutes": DRY_RUN_VALID_MINUTES,
    }


async def set_policy(session: AsyncSession, *, admin: User, category: str, days: int | None) -> dict[str, Any]:
    spec = _BY_KEY.get(category)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown retention category")
    if days is not None and days < spec.minimum_days:
        raise HTTPException(
            status_code=422, detail=f"{spec.label} must be kept at least {spec.minimum_days} days"
        )
    row = await session.get(RetentionPolicy, category)
    before = row.days if row else None
    if row is None:
        row = RetentionPolicy(category=category)
        session.add(row)
    row.days = days
    row.updated_by = admin.id
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.retention.policy",
            resource_type="retention_policy",
            metadata_={"category": category, "before": before, "after": days},
        )
    )
    await session.commit()
    return await retention_state(session)


def _cutoffs(days: dict[str, int | None], now: datetime) -> dict[str, str]:
    return {
        key: (now - timedelta(days=value)).isoformat()
        for key, value in days.items()
        if value is not None
    }


def _stale_sessions(cutoff: datetime):
    last_activity = func.coalesce(func.max(ChatMessage.created_at), ChatSession.created_at)
    return (
        select(ChatSession.id)
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.case_id.is_(None))
        .group_by(ChatSession.id)
        .having(last_activity < cutoff)
    )


def _stale_jobs(cutoff: datetime):
    return select(Job.id).where(Job.status.in_(_TERMINAL_JOBS), Job.updated_at < cutoff)


def _stale_audit(cutoff: datetime):
    return select(AuditLog.id).where(
        AuditLog.timestamp < cutoff, AuditLog.action.not_like("admin.retention.%")
    )


def _stale_cases(cutoff: datetime):
    return select(Case.id).where(Case.status.in_(_CLOSED_CASE_STATUSES), Case.created_at < cutoff)


_STALE = {
    "chat_history": _stale_sessions,
    "job_records": _stale_jobs,
    "audit_logs": _stale_audit,
    "closed_cases": _stale_cases,
}


async def _count(session: AsyncSession, query) -> int:
    return int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)


async def _counts_for(session: AsyncSession, cutoffs: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, value in cutoffs.items():
        counts[key] = await _count(session, _STALE[key](datetime.fromisoformat(value)))
    counts["expired_refresh_tokens"] = int(
        await session.scalar(
            select(func.count())
            .select_from(RevokedRefreshToken)
            .where(RevokedRefreshToken.expires_at < datetime.now(timezone.utc))
        )
        or 0
    )
    return counts


async def dry_run(session: AsyncSession, *, admin: User) -> dict[str, Any]:
    days = await _policy_days(session)
    cutoffs = _cutoffs(days, datetime.now(timezone.utc))
    counts = await _counts_for(session, cutoffs)
    run = RetentionRun(
        kind="dry_run", requested_by=admin.id, policy=days, cutoffs=cutoffs, counts=counts
    )
    session.add(run)
    await session.flush()
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.retention.dry_run",
            resource_type="retention_run",
            resource_id=run.id,
            metadata_={"counts": counts},
        )
    )
    await session.commit()
    await session.refresh(run)
    return {
        "id": str(run.id),
        "counts": counts,
        "cutoffs": cutoffs,
        "policy": days,
        "created_at": run.created_at.isoformat(),
        "expires_at": (run.created_at + timedelta(minutes=DRY_RUN_VALID_MINUTES)).isoformat(),
        "confirmation": PURGE_CONFIRMATION,
    }


async def _erase_case_from_stores(case: Case, retrieval_client: Any, objects: list[StorageObject]) -> None:
    """Everything outside PostgreSQL, before the rows that describe it go.

    In that order so a failure leaves the case in place to retry. The reverse
    would orphan privileged files and passages with nothing left pointing at them.
    """
    await retrieval_client.delete(
        collection_name=collection_for_case_role(case.role_type),
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[models.FieldCondition(key="case_id", match=models.MatchValue(value=str(case.id)))]
            )
        ),
        wait=True,
    )
    if objects:
        client = create_s3_client()
        for stored in objects:
            await asyncio.to_thread(client.delete_object, Bucket=stored.bucket, Key=stored.object_key)


async def _purge_cases(
    session: AsyncSession, cutoff: datetime, retrieval_client: Any
) -> tuple[int, int]:
    purged = failed = 0
    for case_id in (await session.scalars(_stale_cases(cutoff))).all():
        case = await session.get(Case, case_id)
        objects = list(
            (await session.scalars(select(StorageObject).where(StorageObject.case_id == case_id))).all()
        )
        try:
            await _erase_case_from_stores(case, retrieval_client, objects)
        except Exception as exc:  # noqa: BLE001 - this case stays for the next run
            logger.error("retention: case erase failed: %s", type(exc).__name__)
            failed += 1
            continue
        # chat_sessions.case_id is SET NULL, which would leave conversations
        # quoting the deleted matter behind, unattached to anything.
        await session.execute(delete(ChatSession).where(ChatSession.case_id == case_id))
        await session.execute(delete(Case).where(Case.id == case_id))
        await session.commit()
        purged += 1
    return purged, failed


async def purge(
    session: AsyncSession,
    *,
    admin: User,
    dry_run_id: uuid.UUID,
    confirmation: str,
    retrieval_client: Any,
) -> dict[str, Any]:
    if confirmation != PURGE_CONFIRMATION:
        raise HTTPException(status_code=422, detail=f"Type {PURGE_CONFIRMATION} to confirm")
    preview = await session.get(RetentionRun, dry_run_id)
    if preview is None or preview.kind != "dry_run":
        raise HTTPException(status_code=404, detail="Dry run not found")
    if preview.requested_by != admin.id:
        raise HTTPException(status_code=409, detail="Run your own dry run before purging")
    age = datetime.now(timezone.utc) - preview.created_at
    if age > timedelta(minutes=DRY_RUN_VALID_MINUTES):
        raise HTTPException(status_code=409, detail="This dry run has expired. Run it again.")
    if await session.scalar(select(RetentionRun.id).where(RetentionRun.dry_run_id == dry_run_id)):
        raise HTTPException(status_code=409, detail="This dry run has already been used")
    if await _policy_days(session) != preview.policy:
        raise HTTPException(status_code=409, detail="Retention periods changed since this dry run")

    cutoffs = {key: datetime.fromisoformat(value) for key, value in preview.cutoffs.items()}
    deleted: dict[str, int] = {}

    # Claim the dry run first: the unique column stops a second purge from it,
    # and this row survives even if the audit category purges old rows below.
    run = RetentionRun(
        kind="purge",
        dry_run_id=dry_run_id,
        requested_by=admin.id,
        policy=preview.policy,
        cutoffs=preview.cutoffs,
        counts={},
    )
    session.add(run)
    await session.flush()

    if "chat_history" in cutoffs:
        result = await session.execute(
            delete(ChatSession).where(ChatSession.id.in_(_stale_sessions(cutoffs["chat_history"])))
        )
        deleted["chat_history"] = int(result.rowcount or 0)
    if "job_records" in cutoffs:
        result = await session.execute(delete(Job).where(Job.id.in_(_stale_jobs(cutoffs["job_records"]))))
        deleted["job_records"] = int(result.rowcount or 0)
    if "audit_logs" in cutoffs:
        result = await session.execute(
            delete(AuditLog).where(AuditLog.id.in_(_stale_audit(cutoffs["audit_logs"])))
        )
        deleted["audit_logs"] = int(result.rowcount or 0)
    result = await session.execute(
        delete(RevokedRefreshToken).where(RevokedRefreshToken.expires_at < datetime.now(timezone.utc))
    )
    deleted["expired_refresh_tokens"] = int(result.rowcount or 0)
    await session.commit()

    if "closed_cases" in cutoffs:
        purged, failed = await _purge_cases(session, cutoffs["closed_cases"], retrieval_client)
        deleted["closed_cases"] = purged
        if failed:
            deleted["closed_cases_failed"] = failed

    run.counts = deleted
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.retention.purge",
            resource_type="retention_run",
            resource_id=run.id,
            metadata_={"dry_run_id": str(dry_run_id), "deleted": deleted},
        )
    )
    await session.commit()
    return {"id": str(run.id), "dry_run_id": str(dry_run_id), "deleted": deleted}
