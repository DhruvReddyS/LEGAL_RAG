from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.permissions import ADMIN_AUDIT_READ, ADMIN_CORPUS_MANAGE, ADMIN_USER_MANAGE
from app.core.rbac import require_permission
from app.models import AuditLog, Case, CorpusIntake, StorageObject, User
from app.models.enums import CorpusSourceType, UserRole
from app.schemas.admin import (
    AdminOverviewResponse,
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdate,
    AuditEventListResponse,
    AuditEventResponse,
    CorpusIntakeListResponse,
    CorpusIntakeResponse,
    CorpusPublishResponse,
)
from app.services.admin import (
    MAX_CORPUS_UPLOAD_BYTES,
    admin_overview,
    create_professional_user,
    intake_response,
    list_professional_users,
    publish_corpus_intake,
    stage_corpus_intake,
    update_professional_user,
    validate_corpus_intake,
)


router = APIRouter(prefix="/admin", tags=["administration"])


async def _intake_or_404(session: AsyncSession, intake_id: uuid.UUID) -> CorpusIntake:
    intake = await session.get(CorpusIntake, intake_id)
    if intake is None:
        raise HTTPException(status_code=404, detail="Corpus intake not found")
    return intake


@router.get("/overview", response_model=AdminOverviewResponse)
async def overview(
    _: Annotated[User, Depends(require_permission(ADMIN_USER_MANAGE))],
    session: AsyncSession = Depends(get_db_session),
) -> AdminOverviewResponse:
    return await admin_overview(session)


@router.get("/users", response_model=AdminUserListResponse)
async def users(
    _: Annotated[User, Depends(require_permission(ADMIN_USER_MANAGE))],
    session: AsyncSession = Depends(get_db_session),
) -> AdminUserListResponse:
    items = await list_professional_users(session)
    return AdminUserListResponse(users=items, total=len(items))


@router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: AdminUserCreate,
    admin: Annotated[User, Depends(require_permission(ADMIN_USER_MANAGE))],
    session: AsyncSession = Depends(get_db_session),
) -> AdminUserResponse:
    user = await create_professional_user(session, payload, admin)
    return AdminUserResponse.model_validate(user)


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    admin: Annotated[User, Depends(require_permission(ADMIN_USER_MANAGE))],
    session: AsyncSession = Depends(get_db_session),
) -> AdminUserResponse:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    user = await update_professional_user(
        session,
        target,
        role=UserRole(payload.role) if payload.role is not None else None,
        is_active=payload.is_active,
        admin=admin,
    )
    case_count = int(
        await session.scalar(select(func.count(Case.id)).where(Case.owner_id == user.id))
        or 0
    )
    return AdminUserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        case_count=case_count,
    )


@router.get("/corpus/intakes", response_model=CorpusIntakeListResponse)
async def corpus_intakes(
    _: Annotated[User, Depends(require_permission(ADMIN_CORPUS_MANAGE))],
    session: AsyncSession = Depends(get_db_session),
) -> CorpusIntakeListResponse:
    rows = (
        await session.execute(
            select(CorpusIntake, StorageObject)
            .join(StorageObject, StorageObject.id == CorpusIntake.storage_object_id)
            .order_by(CorpusIntake.created_at.desc())
        )
    ).all()
    items = [intake_response(intake, stored) for intake, stored in rows]
    return CorpusIntakeListResponse(intakes=items, total=len(items))


@router.post("/corpus/intakes", response_model=CorpusIntakeResponse, status_code=status.HTTP_201_CREATED)
async def create_corpus_intake(
    admin: Annotated[User, Depends(require_permission(ADMIN_CORPUS_MANAGE))],
    file: UploadFile = File(...),
    title: str = Form(..., min_length=3, max_length=500),
    source_type: CorpusSourceType = Form(...),
    jurisdiction: str = Form(..., min_length=2, max_length=255),
    source_url: str = Form(..., min_length=12, max_length=2000),
    authority: str | None = Form(None, max_length=255),
    session: AsyncSession = Depends(get_db_session),
) -> CorpusIntakeResponse:
    content = await file.read(MAX_CORPUS_UPLOAD_BYTES + 1)
    intake, stored = await stage_corpus_intake(
        session,
        admin=admin,
        filename=file.filename or "corpus.pdf",
        content_type=file.content_type or "application/octet-stream",
        content=content,
        title=title,
        source_type=source_type,
        jurisdiction=jurisdiction,
        authority=authority,
        source_url=source_url,
    )
    return intake_response(intake, stored)


@router.post("/corpus/intakes/{intake_id}/validate", response_model=CorpusIntakeResponse)
async def validate_intake(
    intake_id: uuid.UUID,
    admin: Annotated[User, Depends(require_permission(ADMIN_CORPUS_MANAGE))],
    session: AsyncSession = Depends(get_db_session),
) -> CorpusIntakeResponse:
    intake = await _intake_or_404(session, intake_id)
    intake, stored = await validate_corpus_intake(session, intake=intake, admin=admin)
    return intake_response(intake, stored)


@router.post("/corpus/intakes/{intake_id}/publish", response_model=CorpusPublishResponse)
async def publish_intake(
    intake_id: uuid.UUID,
    request: Request,
    admin: Annotated[User, Depends(require_permission(ADMIN_CORPUS_MANAGE))],
    session: AsyncSession = Depends(get_db_session),
) -> CorpusPublishResponse:
    intake = await _intake_or_404(session, intake_id)
    intake, stored, indexed = await publish_corpus_intake(
        session,
        intake=intake,
        admin=admin,
        retrieval=request.app.state.retrieval_service,
    )
    return CorpusPublishResponse(intake=intake_response(intake, stored), indexed_chunks=indexed)


@router.get("/audit", response_model=AuditEventListResponse)
async def audit_events(
    _: Annotated[User, Depends(require_permission(ADMIN_AUDIT_READ))],
    session: AsyncSession = Depends(get_db_session),
    limit: int = 50,
) -> AuditEventListResponse:
    bounded_limit = max(1, min(limit, 100))
    rows = (
        await session.execute(
            select(AuditLog, User.name)
            .outerjoin(User, User.id == AuditLog.user_id)
            .order_by(AuditLog.timestamp.desc())
            .limit(bounded_limit)
        )
    ).all()
    total = int(await session.scalar(select(func.count(AuditLog.id))) or 0)
    return AuditEventListResponse(
        events=[
            AuditEventResponse(
                id=event.id,
                actor_name=actor_name,
                action=event.action,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                metadata=event.metadata_,
                timestamp=event.timestamp,
            )
            for event, actor_name in rows
        ],
        total=total,
    )
