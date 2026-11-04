"""Searching and organising your own conversations.

Rename and delete stay on /chat/sessions. These routes add what that list lacks:
finding, pinning, naming a matter, and paging past the first thirty.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.permissions import CHAT_USE
from app.core.rbac import require_permission
from app.models import User
from app.schemas.history import (
    HistoryPage,
    HistorySearch,
    HistorySession,
    MatterList,
    MatterUpdate,
    PinUpdate,
)
from app.services import history


router = APIRouter(prefix="/history", tags=["history"])


@router.get("/sessions", response_model=HistoryPage)
async def list_history(
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: Annotated[str | None, Query(max_length=128)] = None,
    pinned: bool | None = None,
    matter: Annotated[str | None, Query(max_length=120)] = None,
    case_id: uuid.UUID | None = None,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> HistoryPage:
    items, next_cursor = await history.list_sessions(
        session,
        user,
        limit=limit,
        cursor=cursor,
        pinned=pinned,
        matter=matter,
        case_id=case_id,
    )
    return HistoryPage(items=[HistorySession(**item) for item in items], next_cursor=next_cursor)


@router.post("/search", response_model=HistoryPage)
async def search_history(
    request: HistorySearch,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> HistoryPage:
    items, next_cursor = await history.list_sessions(
        session,
        user,
        limit=request.limit,
        cursor=request.cursor,
        matter=request.matter,
        case_id=request.case_id,
        term=request.term,
    )
    return HistoryPage(items=[HistorySession(**item) for item in items], next_cursor=next_cursor)


@router.put("/sessions/{session_id}/pin", status_code=status.HTTP_204_NO_CONTENT)
async def pin_session(
    session_id: uuid.UUID,
    request: PinUpdate,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await history.set_pinned(session, session_id, user, request.pinned)
    await session.commit()


@router.put("/sessions/{session_id}/matter", status_code=status.HTTP_204_NO_CONTENT)
async def set_session_matter(
    session_id: uuid.UUID,
    request: MatterUpdate,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await history.set_matter(session, session_id, user, request.matter)
    await session.commit()


@router.get("/matters", response_model=MatterList)
async def list_matters(
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> MatterList:
    return MatterList(items=await history.list_matters(session, user))
