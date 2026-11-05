"""The administration console's API.

Every route requires an administrative permission. None of them search private
case material, and any that touches a user's conversation writes an audit row
without its text.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, AsyncIterator, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompt_registry import prompt_versions
from app.core.config import settings
from app.core.database import get_db_session
from app.core.permissions import ADMIN_AUDIT_READ, ADMIN_CORPUS_MANAGE, ADMIN_USER_MANAGE
from app.core.qdrant import create_qdrant_client
from app.core.rbac import require_permission
from app.models import AuditLog, Job, User
from app.models.enums import JobStatus, UserRole
from app.services import (
    admin_corpus,
    admin_evidence,
    admin_incidents,
    admin_quality,
    admin_release,
    admin_retention,
    admin_users,
    amendment_watch,
    expert_review,
    law_changes,
    quarantine,
)
from app.services.audit_redaction import redact_audit_metadata
from app.services.health import is_small_tier_model, readiness_report

router = APIRouter(prefix="/admin/console", tags=["administration-console"])

CorpusAdmin = Annotated[User, Depends(require_permission(ADMIN_CORPUS_MANAGE))]
UserAdmin = Annotated[User, Depends(require_permission(ADMIN_USER_MANAGE))]
AuditAdmin = Annotated[User, Depends(require_permission(ADMIN_AUDIT_READ))]
Db = Annotated[AsyncSession, Depends(get_db_session)]
Page = Annotated[int, Query(ge=1, le=100_000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


async def get_corpus_client(request: Request) -> AsyncIterator[Any]:
    """The serving vector client, or a short-lived one before startup has run."""
    service = getattr(request.app.state, "retrieval_service", None)
    if service is not None:
        yield service.client
        return
    client = create_qdrant_client()
    try:
        yield client
    finally:
        await client.close()


CorpusClient = Annotated[Any, Depends(get_corpus_client)]


# ----------------------------------------------------------------- release


class ReleaseDecisionRequest(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    collection: str = Field(min_length=1, max_length=128)
    decision: Literal["approve", "refuse"]
    reason: str = Field(min_length=10, max_length=2000)
    override_failed_gates: bool = False


class GateRunRequest(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    collection: str = Field(min_length=1, max_length=128)
    # The queue is the guard. This is the person saying they read it.
    confirm: Literal[True]


class CutoverPlanRequest(BaseModel):
    collection: str = Field(min_length=1, max_length=128)
    confirm_collection: str = Field(min_length=1, max_length=128)


@router.get("/release")
async def release(admin: CorpusAdmin, session: Db, client: CorpusClient) -> dict[str, Any]:
    return await admin_release.release_state(session, client)


@router.get("/release/{label}/documents/{name}")
async def release_document(label: str, name: str, admin: CorpusAdmin) -> dict[str, str]:
    content = await asyncio.to_thread(admin_release.read_gate_document, label, name)
    return {"name": name, "content": content}


@router.post("/release/decisions", status_code=201)
async def release_decision(
    payload: ReleaseDecisionRequest, admin: CorpusAdmin, session: Db
) -> dict[str, Any]:
    return await admin_release.record_decision(
        session,
        admin=admin,
        label=payload.label,
        collection=payload.collection,
        decision=payload.decision,
        reason=" ".join(payload.reason.split()),
        override_failed_gates=payload.override_failed_gates,
    )


@router.post("/release/cutover-plan")
async def release_cutover_plan(
    payload: CutoverPlanRequest, admin: CorpusAdmin, session: Db
) -> dict[str, Any]:
    return await admin_release.cutover_plan(
        session,
        admin=admin,
        collection=payload.collection,
        confirm_collection=payload.confirm_collection,
    )


@router.post("/release/gate-runs", status_code=202)
async def queue_gates(
    payload: GateRunRequest, admin: CorpusAdmin, session: Db, client: CorpusClient
) -> dict[str, Any]:
    return await admin_release.queue_gate_run(
        session, admin=admin, client=client, label=payload.label, collection=payload.collection
    )


@router.post("/release/gate-runs/{run_id}/cancel")
async def cancel_gates(run_id: uuid.UUID, admin: CorpusAdmin, session: Db) -> dict[str, Any]:
    return await admin_release.cancel_gate_run(session, admin=admin, run_id=run_id)


# ------------------------------------------------------------------ corpus


class WorkItemRequest(BaseModel):
    canonical_document_id: str = Field(min_length=1, max_length=128)
    queue: Literal["ocr", "verification", "currency"]
    status: Literal["open", "in_progress", "done"]
    note: str | None = Field(default=None, max_length=1000)


@router.get("/corpus")
async def corpus(
    admin: CorpusAdmin,
    session: Db,
    q: Annotated[str, Query(max_length=200)] = "",
    source_type: Annotated[str | None, Query(max_length=64)] = None,
    domain: Annotated[str | None, Query(max_length=128)] = None,
    currency: Annotated[str | None, Query(max_length=32)] = None,
    queue: Literal["ocr", "verification", "currency"] | None = None,
    work_status: Literal["open", "in_progress", "done"] | None = None,
    page: Page = 1,
    page_size: PageSize = 25,
) -> dict[str, Any]:
    return await admin_corpus.browse_corpus(
        session,
        q=q,
        source_type=source_type,
        domain=domain,
        currency=currency,
        queue=queue,
        work_status=work_status,
        page=page,
        page_size=page_size,
    )


@router.put("/corpus/work-items")
async def corpus_work_item(payload: WorkItemRequest, admin: CorpusAdmin, session: Db) -> dict[str, Any]:
    return await admin_corpus.set_work_item(
        session,
        admin=admin,
        canonical_document_id=payload.canonical_document_id,
        queue=payload.queue,
        status=payload.status,
        note=payload.note,
    )


class AmendmentReviewRequest(BaseModel):
    status: Literal["open", "reviewed", "dismissed"]
    note: str | None = Field(default=None, max_length=2000)


@router.get("/corpus/amendments")
async def corpus_amendments(
    admin: CorpusAdmin, session: Db, page: Page = 1, page_size: PageSize = 25
) -> dict[str, Any]:
    return await amendment_watch.console_view(
        session, Path(settings.legal_kb_root), page=page, page_size=page_size
    )


@router.put("/corpus/amendments/findings/{finding_id}")
async def corpus_amendment_review(
    finding_id: str, payload: AmendmentReviewRequest, admin: CorpusAdmin, session: Db
) -> dict[str, Any]:
    return await amendment_watch.review_finding(
        session,
        Path(settings.legal_kb_root),
        admin=admin,
        finding_id=finding_id,
        status=payload.status,
        note=payload.note,
    )


@router.post("/corpus/currency-notices/sync")
async def corpus_currency_sync(admin: CorpusAdmin, session: Db) -> dict[str, Any]:
    """Run the daily comparison now, after someone has edited the currency table."""
    return await law_changes.sync_currency_notices(session)


# ----------------------------------------------------------------- quality


class ReviewSampleRequest(BaseModel):
    count: int = Field(ge=1, le=50)
    days: int = Field(default=30, ge=1, le=365)


class ClaimVerdictRequest(BaseModel):
    # Null clears a verdict given by mistake, and the claim is unreviewed again.
    verdict: Literal["correct", "incorrect", "unsure"] | None
    note: str | None = Field(default=None, max_length=2000)


@router.get("/quality")
async def quality(
    admin: CorpusAdmin, session: Db, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> dict[str, Any]:
    return await admin_quality.quality_dashboard(session, days)


@router.get("/quality/review")
async def quality_review(
    admin: CorpusAdmin,
    session: Db,
    status: Literal["open", "done"] = "open",
    page: Page = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    return await expert_review.review_queue(session, status=status, page=page, page_size=page_size)


@router.post("/quality/review/sample", status_code=201)
async def quality_review_sample(
    payload: ReviewSampleRequest, admin: CorpusAdmin, session: Db
) -> dict[str, Any]:
    return await expert_review.sample_answers(session, admin=admin, count=payload.count, days=payload.days)


@router.put("/quality/review/claims/{claim_id}")
async def quality_review_verdict(
    claim_id: uuid.UUID, payload: ClaimVerdictRequest, admin: CorpusAdmin, session: Db
) -> dict[str, Any]:
    return await expert_review.record_verdict(
        session, admin=admin, claim_id=claim_id, verdict=payload.verdict, note=payload.note
    )


# --------------------------------------------------------------- incidents


class TriageRequest(BaseModel):
    status: Literal["open", "investigating", "resolved", "dismissed"]
    note: str | None = Field(default=None, max_length=1000)


class QuarantinePreviewRequest(BaseModel):
    canonical_document_id: str = Field(min_length=1, max_length=128)


class QuarantineRequest(QuarantinePreviewRequest):
    reason: str = Field(min_length=10, max_length=2000)
    feedback_id: uuid.UUID | None = None
    confirm: Literal[True]


class QuarantineReleaseRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)
    confirm: Literal[True]


@router.get("/feedback")
async def feedback(
    admin: CorpusAdmin,
    session: Db,
    rating: Literal["up", "down"] | None = None,
    status: Literal["open", "investigating", "resolved", "dismissed"] | None = None,
    page: Page = 1,
    page_size: PageSize = 25,
) -> dict[str, Any]:
    return await admin_incidents.list_feedback(
        session, rating=rating, status=status, page=page, page_size=page_size
    )


@router.get("/feedback/{feedback_id}/trace")
async def feedback_trace(
    feedback_id: uuid.UUID, admin: CorpusAdmin, session: Db, client: CorpusClient
) -> dict[str, Any]:
    return await admin_incidents.trace_feedback(
        session, admin=admin, feedback_id=feedback_id, client=client
    )


@router.put("/feedback/{feedback_id}/triage")
async def feedback_triage(
    feedback_id: uuid.UUID, payload: TriageRequest, admin: CorpusAdmin, session: Db
) -> dict[str, Any]:
    return await admin_incidents.update_triage(
        session, admin=admin, feedback_id=feedback_id, status=payload.status, note=payload.note
    )


@router.get("/quarantine")
async def quarantine_list(
    admin: CorpusAdmin, session: Db, include_released: bool = False
) -> dict[str, Any]:
    return {
        "quarantines": await admin_incidents.list_quarantines(
            session, include_released=include_released
        )
    }


@router.post("/quarantine/preview")
async def quarantine_preview(
    payload: QuarantinePreviewRequest, admin: CorpusAdmin, session: Db, client: CorpusClient
) -> dict[str, Any]:
    return await admin_incidents.preview_quarantine(
        session, canonical_document_id=payload.canonical_document_id, client=client
    )


@router.post("/quarantine", status_code=201)
async def quarantine_create(payload: QuarantineRequest, admin: CorpusAdmin, session: Db) -> dict[str, Any]:
    return await admin_incidents.quarantine_document(
        session,
        admin=admin,
        canonical_document_id=payload.canonical_document_id,
        reason=" ".join(payload.reason.split()),
        feedback_id=payload.feedback_id,
    )


@router.post("/quarantine/{quarantine_id}/release")
async def quarantine_release(
    quarantine_id: uuid.UUID, payload: QuarantineReleaseRequest, admin: CorpusAdmin, session: Db
) -> dict[str, Any]:
    return await admin_incidents.release_document(
        session, admin=admin, quarantine_id=quarantine_id, reason=" ".join(payload.reason.split())
    )


# ------------------------------------------------------------------- users


class SuspendRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)
    confirm: Literal[True]


class ConfirmRequest(BaseModel):
    confirm: Literal[True]


class RoleRequest(BaseModel):
    role: Literal["citizen", "police", "advocate"]
    confirm: Literal[True]


class RequiredRequest(BaseModel):
    required: bool


@router.get("/users")
async def users(
    admin: UserAdmin,
    session: Db,
    q: Annotated[str, Query(max_length=200)] = "",
    role: Literal["citizen", "police", "advocate", "admin"] | None = None,
    status: Literal["active", "suspended"] | None = None,
    page: Page = 1,
    page_size: PageSize = 25,
) -> dict[str, Any]:
    return await admin_users.list_users(
        session, q=q, role=role, status=status, page=page, page_size=page_size
    )


@router.post("/users/{user_id}/suspend")
async def user_suspend(
    user_id: uuid.UUID, payload: SuspendRequest, admin: UserAdmin, session: Db
) -> dict[str, Any]:
    return await admin_users.suspend_user(
        session, admin=admin, user_id=user_id, reason=" ".join(payload.reason.split())
    )


@router.post("/users/{user_id}/reactivate")
async def user_reactivate(
    user_id: uuid.UUID, payload: ConfirmRequest, admin: UserAdmin, session: Db
) -> dict[str, Any]:
    return await admin_users.reactivate_user(session, admin=admin, user_id=user_id)


@router.post("/users/{user_id}/revoke-sessions")
async def user_revoke_sessions(
    user_id: uuid.UUID, payload: ConfirmRequest, admin: UserAdmin, session: Db
) -> dict[str, Any]:
    return await admin_users.revoke_sessions(session, admin=admin, user_id=user_id)


@router.post("/users/{user_id}/force-password-reset")
async def user_force_password_reset(
    user_id: uuid.UUID, payload: RequiredRequest, admin: UserAdmin, session: Db
) -> dict[str, Any]:
    return await admin_users.force_password_reset(
        session, admin=admin, user_id=user_id, required=payload.required
    )


@router.post("/users/{user_id}/mfa-required")
async def user_mfa_required(
    user_id: uuid.UUID, payload: RequiredRequest, admin: UserAdmin, session: Db
) -> dict[str, Any]:
    return await admin_users.set_mfa_required(
        session, admin=admin, user_id=user_id, required=payload.required
    )


@router.post("/users/{user_id}/role")
async def user_role(
    user_id: uuid.UUID, payload: RoleRequest, admin: UserAdmin, session: Db
) -> dict[str, Any]:
    return await admin_users.change_role(
        session, admin=admin, user_id=user_id, role=UserRole(payload.role)
    )


# --------------------------------------------------------------- retention


class RetentionPolicyRequest(BaseModel):
    days: int | None = Field(default=None, ge=1, le=36_500)


class PurgeRequest(BaseModel):
    dry_run_id: uuid.UUID
    confirmation: str = Field(max_length=16)


@router.get("/retention")
async def retention(admin: UserAdmin, session: Db) -> dict[str, Any]:
    return await admin_retention.retention_state(session)


@router.put("/retention/{category}")
async def retention_policy(
    category: str, payload: RetentionPolicyRequest, admin: UserAdmin, session: Db
) -> dict[str, Any]:
    return await admin_retention.set_policy(session, admin=admin, category=category, days=payload.days)


@router.post("/retention/dry-run", status_code=201)
async def retention_dry_run(admin: UserAdmin, session: Db) -> dict[str, Any]:
    return await admin_retention.dry_run(session, admin=admin)


@router.post("/retention/purge")
async def retention_purge(
    payload: PurgeRequest, admin: UserAdmin, session: Db, client: CorpusClient
) -> dict[str, Any]:
    return await admin_retention.purge(
        session,
        admin=admin,
        dry_run_id=payload.dry_run_id,
        confirmation=payload.confirmation,
        retrieval_client=client,
    )


# ------------------------------------------------------------------ models


@router.get("/models")
async def model_configuration(admin: CorpusAdmin) -> dict[str, Any]:
    fingerprints = await asyncio.to_thread(prompt_versions)
    runs = await asyncio.to_thread(admin_evidence.list_evaluation_runs)
    latest = next((run for run in runs if run.prompt_versions), None)
    return {
        "generation": {
            "model": settings.ollama_model,
            "concurrency": settings.ollama_generation_concurrency,
            "keep_alive": settings.ollama_keep_alive,
            "small_tier": is_small_tier_model(settings.ollama_model),
        },
        "serving_collection": settings.qdrant_global_collection,
        "prompts": [
            {
                "name": name,
                "fingerprint": value,
                # Against the newest run that recorded prompts: a mismatch means
                # today's prompt has not been measured.
                "measured_in_latest_run": (
                    latest.prompt_versions.get(name) == value if latest else None
                ),
            }
            for name, value in sorted(fingerprints.items())
        ],
        "latest_run": latest.id if latest else None,
        "change_steps": [
            {
                "title": "Set the model",
                "command": "OLLAMA_MODEL=<model>",
                "detail": (
                    "Read once at startup, and checked there: a small-tier model is refused "
                    "because it would approve claims it should reject."
                ),
            },
            {
                "title": "Restart, then measure",
                "command": "./scripts/run_corpus_gates.sh <collection> <label>",
                "detail": "Prompts change only with the code. A new fingerprint needs a new run to compare.",
            },
        ],
    }


@router.get("/evaluations")
async def evaluations(admin: CorpusAdmin) -> dict[str, Any]:
    runs = await asyncio.to_thread(admin_evidence.list_evaluation_runs)
    return {"runs": [run.summary() for run in runs]}


@router.get("/evaluations/compare")
async def evaluations_compare(
    admin: CorpusAdmin,
    a: Annotated[str, Query(max_length=200)],
    b: Annotated[str, Query(max_length=200)],
) -> dict[str, Any]:
    # Ids come from the listing and are only ever matched against it, so this
    # never turns a request parameter into a path.
    runs = {run.id: run for run in await asyncio.to_thread(admin_evidence.list_evaluation_runs)}
    if a not in runs or b not in runs:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return admin_evidence.compare_runs(runs[a], runs[b])


# ------------------------------------------------------------------- audit


@router.get("/audit")
async def audit(
    admin: AuditAdmin,
    session: Db,
    action: Annotated[str | None, Query(max_length=100)] = None,
    actor: Annotated[str | None, Query(max_length=200)] = None,
    resource_type: Annotated[str | None, Query(max_length=100)] = None,
    resource_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: Page = 1,
    page_size: PageSize = 50,
) -> dict[str, Any]:
    filters = []
    if action:
        filters.append(AuditLog.action.startswith(action, autoescape=True))
    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)
    if resource_id:
        filters.append(AuditLog.resource_id == resource_id)
    if since:
        filters.append(AuditLog.timestamp >= since)
    if until:
        filters.append(AuditLog.timestamp <= until)
    if actor:
        pattern = "%" + actor.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        filters.append(
            or_(User.name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\"))
        )
    joined = select(AuditLog.id).outerjoin(User, User.id == AuditLog.user_id).where(*filters)
    total = int(await session.scalar(select(func.count()).select_from(joined.subquery())) or 0)
    rows = (
        await session.execute(
            select(AuditLog, User.name, User.email)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(*filters)
            .order_by(AuditLog.timestamp.desc(), AuditLog.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    actions = (
        await session.scalars(select(distinct(AuditLog.action)).order_by(AuditLog.action).limit(200))
    ).all()
    resource_types = (
        await session.scalars(
            select(distinct(AuditLog.resource_type)).order_by(AuditLog.resource_type).limit(100)
        )
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "actions": list(actions),
        "resource_types": list(resource_types),
        "events": [
            {
                "id": str(event.id),
                "actor_name": name,
                "actor_email": email,
                "action": event.action,
                "resource_type": event.resource_type,
                "resource_id": str(event.resource_id) if event.resource_id else None,
                "metadata": redact_audit_metadata(event.metadata_),
                "timestamp": event.timestamp.isoformat(),
            }
            for event, name, email in rows
        ],
    }


# ------------------------------------------------------------------ health


@router.get("/health")
async def system_health(admin: CorpusAdmin, session: Db) -> dict[str, Any]:
    ready, report = await readiness_report()
    by_status = (await session.execute(select(Job.status, func.count(Job.id)).group_by(Job.status))).all()
    oldest_queued = await session.scalar(
        select(func.min(Job.created_at)).where(Job.status == JobStatus.QUEUED)
    )
    # Metadata only: a job's payload and result hold what somebody asked.
    recent = (
        await session.execute(
            select(Job.id, Job.type, Job.status, Job.progress, Job.attempt_count, Job.error_code, Job.created_at)
            .order_by(Job.created_at.desc())
            .limit(15)
        )
    ).all()
    revision = await session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    return {
        "ready": ready,
        "report": report,
        "environment": settings.app_env,
        "serving_collection": settings.qdrant_global_collection,
        "schema_revision": revision,
        "job_worker_enabled": settings.job_worker_enabled,
        "quarantined_documents": len(quarantine.quarantined_document_ids()),
        "jobs": {
            "by_status": {status.value: int(count) for status, count in by_status},
            "oldest_queued_at": oldest_queued.isoformat() if oldest_queued else None,
            "recent": [
                {
                    "id": str(row[0]),
                    "type": row[1].value,
                    "status": row[2].value,
                    "progress": row[3],
                    "attempts": row[4],
                    "error_code": row[5],
                    "created_at": row[6].isoformat(),
                }
                for row in recent
            ],
        },
    }
