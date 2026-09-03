from __future__ import annotations

import hashlib
import json
import re
import uuid
import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db_session
from app.core.permissions import CASE_DOCUMENT_MANAGE_OWN, CHAT_USE
from app.core.rbac import require_permission
from app.models import (
    AuditLog,
    Case,
    CaseDocument,
    ChatMessage,
    ChatSession,
    Job,
    JobEvent,
    StorageObject,
    User,
)
from app.models.enums import ChatMessageRole, JobStatus, JobType, UserRole
from app.schemas.jobs import (
    DeepReviewJobRequest,
    DocumentAnalysisJobRequest,
    JobListResponse,
    JobEventResponse,
    JobResponse,
    OcrIngestionJobRequest,
)
from app.services.jobs import (
    TERMINAL_JOB_STATUSES,
    append_job_event,
    owned_jobs_query,
    request_job_cancellation,
)
from app.services.rate_limit import RateLimitExceeded, user_rate_limiter
from app.core.config import settings


router = APIRouter(prefix="/jobs", tags=["jobs"])
IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def _request_fingerprint(request: BaseModel) -> str:
    canonical = json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_idempotency_key(idempotency_key: str) -> None:
    if not IDEMPOTENCY_KEY_RE.fullmatch(idempotency_key):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Idempotency-Key must be 8-128 URL-safe characters",
        )


async def _idempotent_job(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    job_type: JobType,
    idempotency_key: str,
    fingerprint: str,
) -> Job | None:
    existing = await session.scalar(
        select(Job).where(
            Job.user_id == user_id,
            Job.type == job_type,
            Job.idempotency_key == idempotency_key,
        )
    )
    if existing is not None and existing.payload.get("request_fingerprint") != fingerprint:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used for a different request",
        )
    return existing


async def _persist_job(
    session: AsyncSession,
    *,
    user: User,
    job_type: JobType,
    idempotency_key: str,
    payload: dict,
    audit_metadata: dict,
) -> Job:
    job = Job(
        user_id=user.id,
        type=job_type,
        status=JobStatus.QUEUED,
        progress=0,
        idempotency_key=idempotency_key,
        payload=payload,
        max_attempts=3,
    )
    session.add(job)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        winner = await _idempotent_job(
            session,
            user_id=user.id,
            job_type=job_type,
            idempotency_key=idempotency_key,
            fingerprint=str(payload["request_fingerprint"]),
        )
        if winner is None:
            raise HTTPException(status_code=409, detail="Idempotency conflict")
        return winner
    append_job_event(
        session,
        job,
        event_type="status",
        stage="queued",
        data={"status": JobStatus.QUEUED.value},
    )
    session.add(
        AuditLog(
            user_id=user.id,
            action="job.enqueue",
            resource_type="job",
            resource_id=job.id,
            metadata_={"job_type": job.type.value, **audit_metadata},
        )
    )
    await session.commit()
    await session.refresh(job)
    return job


async def _admit_job_enqueue(user: User) -> None:
    try:
        await user_rate_limiter.admit(
            str(user.id),
            "job_enqueue",
            limit=settings.job_enqueues_per_minute,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Per-user job enqueue limit reached",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


async def _owned_chat_session(
    session: AsyncSession,
    session_id: uuid.UUID,
    user: User,
) -> ChatSession:
    chat_session = await session.scalar(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id)
    )
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if chat_session.user_id != user.id and user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You do not own this chat session")
    return chat_session


async def _validate_case(
    session: AsyncSession,
    case_id: uuid.UUID,
    user: User,
) -> Case:
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.owner_id != user.id and user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You do not own this case")
    if user.role in {UserRole.POLICE, UserRole.ADVOCATE} and case.role_type.value != user.role.value:
        raise HTTPException(status_code=403, detail="Case role does not match the current user role")
    return case


async def _owned_job(session: AsyncSession, job_id: uuid.UUID, user: User) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user_id != user.id and user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You do not own this job")
    return job


@router.post(
    "/deep-review",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_deep_review(
    request: DeepReviewJobRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> Job:
    _validate_idempotency_key(idempotency_key)
    fingerprint = _request_fingerprint(request)
    existing = await _idempotent_job(
        session,
        user_id=user.id,
        job_type=JobType.DEEP_REVIEW,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )
    if existing is not None:
        return existing
    await _admit_job_enqueue(user)

    if request.session_id is None:
        if request.case_id is not None:
            await _validate_case(session, request.case_id, user)
        chat_session = ChatSession(
            user_id=user.id,
            case_id=request.case_id,
            title=request.query[:120],
        )
        session.add(chat_session)
        await session.flush()
        history: list[dict[str, str]] = []
    else:
        chat_session = await _owned_chat_session(session, request.session_id, user)
        if request.case_id is not None and request.case_id != chat_session.case_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="case_id does not match the existing chat session",
            )
        history = [
            {"role": message.role.value, "content": message.content}
            for message in chat_session.messages[-8:]
        ]

    user_message = ChatMessage(
        session_id=chat_session.id,
        role=ChatMessageRole.USER,
        content=request.query,
        citations=[],
    )
    session.add(user_message)
    await session.flush()
    return await _persist_job(
        session,
        user=user,
        job_type=JobType.DEEP_REVIEW,
        idempotency_key=idempotency_key,
        payload={
            "request_fingerprint": fingerprint,
            "query": request.query,
            "role": user.role.value,
            "chat_session_id": str(chat_session.id),
            "case_id": str(chat_session.case_id) if chat_session.case_id else None,
            "history": history,
            "user_message_id": str(user_message.id),
        },
        audit_metadata={
            "chat_session_id": str(chat_session.id),
            "case_id": str(chat_session.case_id) if chat_session.case_id else None,
        },
    )


@router.post(
    "/ocr-ingestion",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_ocr_ingestion(
    request: OcrIngestionJobRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    user: User = Depends(
        require_permission(CASE_DOCUMENT_MANAGE_OWN, infer_case_id=False)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> Job:
    _validate_idempotency_key(idempotency_key)
    fingerprint = _request_fingerprint(request)
    existing = await _idempotent_job(
        session,
        user_id=user.id,
        job_type=JobType.OCR_INGESTION,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )
    if existing is not None:
        return existing
    await _admit_job_enqueue(user)
    await _validate_case(session, request.case_id, user)
    stored = await session.get(StorageObject, request.object_id)
    if stored is None or stored.case_id != request.case_id:
        raise HTTPException(status_code=404, detail="Object not found")
    if stored.owner_id != user.id and user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You do not own this object")
    return await _persist_job(
        session,
        user=user,
        job_type=JobType.OCR_INGESTION,
        idempotency_key=idempotency_key,
        payload={
            "request_fingerprint": fingerprint,
            "case_id": str(request.case_id),
            "object_id": str(request.object_id),
            "doc_type": request.doc_type.strip().lower(),
        },
        audit_metadata={"case_id": str(request.case_id), "object_id": str(request.object_id)},
    )


@router.post(
    "/document-analysis",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_document_analysis(
    request: DocumentAnalysisJobRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    user: User = Depends(
        require_permission(CASE_DOCUMENT_MANAGE_OWN, infer_case_id=False)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> Job:
    _validate_idempotency_key(idempotency_key)
    fingerprint = _request_fingerprint(request)
    existing = await _idempotent_job(
        session,
        user_id=user.id,
        job_type=JobType.DOCUMENT_ANALYSIS,
        idempotency_key=idempotency_key,
        fingerprint=fingerprint,
    )
    if existing is not None:
        return existing
    await _admit_job_enqueue(user)
    await _validate_case(session, request.case_id, user)
    document = await session.get(CaseDocument, request.document_id)
    if document is None or document.case_id != request.case_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return await _persist_job(
        session,
        user=user,
        job_type=JobType.DOCUMENT_ANALYSIS,
        idempotency_key=idempotency_key,
        payload={
            "request_fingerprint": fingerprint,
            "case_id": str(request.case_id),
            "document_id": str(request.document_id),
            "focus": request.focus,
        },
        audit_metadata={
            "case_id": str(request.case_id),
            "document_id": str(request.document_id),
        },
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> JobListResponse:
    query = owned_jobs_query(user.id, include_all=user.role is UserRole.ADMIN)
    if job_status is not None:
        query = query.where(Job.status == job_status)
    jobs = list((await session.scalars(query.order_by(Job.created_at.desc()).limit(limit))).all())
    return JobListResponse(items=[JobResponse.model_validate(job) for job in jobs])


@router.get("/{job_id}", response_model=JobResponse)
async def read_job(
    job_id: uuid.UUID,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> JobResponse:
    job = await _owned_job(session, job_id, user)
    response = JobResponse.model_validate(job)
    latest = await session.scalar(
        select(JobEvent)
        .where(JobEvent.job_id == job_id, JobEvent.event_type == "stage")
        .order_by(JobEvent.id.desc())
        .limit(1)
    )
    if latest is not None:
        response.stage = latest.stage
        response.stage_label = latest.data.get("label")
    return response


def _sse_event(event: JobEvent) -> str:
    payload = JobEventResponse.model_validate(event).model_dump(mode="json")
    return (
        f"id: {event.id}\n"
        f"event: {event.event_type}\n"
        f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
    )


@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: uuid.UUID,
    request: Request,
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    await _owned_job(session, job_id, user)
    cursor = after
    if last_event_id is not None:
        try:
            cursor = max(cursor, int(last_event_id))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Last-Event-ID must be an integer") from exc

    async def events():
        current = cursor
        idle_polls = 0
        while not await request.is_disconnected():
            async with session.begin_nested():
                rows = list(
                    (
                        await session.scalars(
                            select(JobEvent)
                            .where(JobEvent.job_id == job_id, JobEvent.id > current)
                            .order_by(JobEvent.id)
                            .limit(100)
                        )
                    ).all()
                )
                job_status = await session.scalar(select(Job.status).where(Job.id == job_id))
            if rows:
                idle_polls = 0
                for event in rows:
                    current = event.id
                    yield _sse_event(event)
            else:
                idle_polls += 1
                if idle_polls >= 20:
                    idle_polls = 0
                    yield ": keep-alive\n\n"
            if job_status in TERMINAL_JOB_STATUSES and not rows:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: uuid.UUID,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> Job:
    job = await _owned_job(session, job_id, user)
    try:
        request_job_cancellation(job)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    append_job_event(
        session,
        job,
        event_type="status",
        stage="cancelled" if job.status is JobStatus.CANCELLED else "cancellation_requested",
        data={"status": job.status.value, "cancel_requested": True},
    )
    session.add(
        AuditLog(
            user_id=user.id,
            action="job.cancel_requested",
            resource_type="job",
            resource_id=job.id,
            metadata_={"status": job.status.value},
        )
    )
    await session.commit()
    await session.refresh(job)
    return job
