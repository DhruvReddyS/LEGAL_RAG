"""Tools a citizen uses on their own situation: C-03 and C-10.

Everything else in the citizen track is client side on purpose. Rights, the
forum router, legal aid and drafting have to work offline or must not send a
person's facts anywhere, so they never reach this router.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.india_time import india_today
from app.core.database import get_db_session
from app.core.permissions import CHAT_USE
from app.core.rbac import require_permission
from app.models import AuditLog, CitizenDeadline, User
from app.schemas.citizen_tools import (
    DeadlineCreate,
    DeadlineListResponse,
    DeadlineResponse,
    DeadlineUpdate,
    NoticeExplainRequest,
    NoticeExplainResponse,
)
from app.services.citizen_notice import explain_notice, plain_language_summary
from app.services.llm import OllamaClient
from app.services.rate_limit import RateLimitExceeded, user_rate_limiter

router = APIRouter(prefix="/citizen", tags=["citizen-tools"])

MAX_DEADLINES_PER_USER = 200
PLAIN_LANGUAGE_TIMEOUT_SECONDS = 240
# A deadline is a calendar date in the place the user lives.


def get_notice_llm() -> OllamaClient:
    return OllamaClient()


async def _admit(user: User, bucket: str, limit: int) -> None:
    try:
        await user_rate_limiter.admit(str(user.id), bucket, limit=limit)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again shortly.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


@router.post("/tools/notice/explain", response_model=NoticeExplainResponse)
async def explain_a_notice(
    request: NoticeExplainRequest,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
    llm: OllamaClient = Depends(get_notice_llm),
) -> dict:
    await _admit(user, "citizen_notice", 20)
    result = explain_notice(request.text)
    if request.plain_language:
        await _admit(user, "citizen_notice_plain", 3)
        try:
            plain, plain_status = await asyncio.wait_for(
                plain_language_summary(llm, request.text, request.language),
                timeout=PLAIN_LANGUAGE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            plain, plain_status = None, "unavailable"
        result["plain"] = plain
        result["plain_status"] = plain_status
    # The type and nothing else: a legal notice is exactly the sort of text an
    # audit row must not become the durable copy of.
    session.add(
        AuditLog(
            user_id=user.id,
            action="citizen.notice_explain",
            resource_type="citizen_tool",
            metadata_={"notice_type": result["notice_type"], "plain_status": result["plain_status"]},
        )
    )
    await session.commit()
    return result


def _today() -> date:
    return india_today()


def _present(row: CitizenDeadline, today: date) -> DeadlineResponse:
    days_left = (row.due_on - today).days
    if row.completed_at is not None:
        state = "done"
    elif days_left < 0:
        state = "overdue"
    elif days_left == 0:
        state = "due_today"
    elif days_left <= row.remind_days_before:
        state = "due_soon"
    else:
        state = "upcoming"
    return DeadlineResponse(
        id=row.id,
        title=row.title,
        due_on=row.due_on,
        remind_days_before=row.remind_days_before,
        notes=row.notes,
        source=row.source,
        provision_label=row.provision_label,
        completed_at=row.completed_at,
        created_at=row.created_at,
        status=state,
        days_left=days_left,
    )


async def _owned(session: AsyncSession, deadline_id: uuid.UUID, user: User) -> CitizenDeadline:
    # Someone else's row is not "forbidden", it does not exist for this reader.
    row = await session.scalar(
        select(CitizenDeadline).where(CitizenDeadline.id == deadline_id, CitizenDeadline.user_id == user.id)
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Date not found")
    return row


@router.get("/matter/deadlines", response_model=DeadlineListResponse)
async def list_deadlines(
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> DeadlineListResponse:
    rows = (
        await session.scalars(
            select(CitizenDeadline)
            .where(CitizenDeadline.user_id == user.id)
            .order_by(
                CitizenDeadline.completed_at.is_not(None),
                CitizenDeadline.due_on,
                CitizenDeadline.created_at,
            )
        )
    ).all()
    today = _today()
    return DeadlineListResponse(items=[_present(row, today) for row in rows], today=today)


@router.post("/matter/deadlines", response_model=DeadlineResponse, status_code=status.HTTP_201_CREATED)
async def create_deadline(
    request: DeadlineCreate,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> DeadlineResponse:
    count = await session.scalar(
        select(func.count()).select_from(CitizenDeadline).where(CitizenDeadline.user_id == user.id)
    )
    if (count or 0) >= MAX_DEADLINES_PER_USER:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Remove an old date before adding another")
    row = CitizenDeadline(user_id=user.id, **request.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _present(row, _today())


@router.patch("/matter/deadlines/{deadline_id}", response_model=DeadlineResponse)
async def update_deadline(
    deadline_id: uuid.UUID,
    request: DeadlineUpdate,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> DeadlineResponse:
    row = await _owned(session, deadline_id, user)
    changes = request.model_dump(exclude_unset=True)
    completed = changes.pop("completed", None)
    for field, value in changes.items():
        # Only notes may be cleared. A null name or date is not a change.
        if field in {"title", "due_on", "remind_days_before"} and value is None:
            continue
        setattr(row, field, value)
    if completed is not None:
        row.completed_at = datetime.now(timezone.utc) if completed else None
    await session.commit()
    await session.refresh(row)
    return _present(row, _today())


@router.delete("/matter/deadlines/{deadline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deadline(
    deadline_id: uuid.UUID,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    row = await _owned(session, deadline_id, user)
    await session.delete(row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
