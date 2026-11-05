"""A person's own notices that the law behind a saved answer has changed."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import get_current_user
from app.models import User
from app.services import law_changes

router = APIRouter(prefix="/account/law-changes", tags=["account"])

CurrentUser = Annotated[User, Depends(get_current_user)]
Db = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("")
async def my_notices(user: CurrentUser, session: Db) -> dict[str, Any]:
    return await law_changes.notices_for(session, user.id)


@router.post("/read-all")
async def read_all(user: CurrentUser, session: Db) -> dict[str, int]:
    return {"marked_read": await law_changes.mark_all_read(session, user.id)}


@router.post("/{notice_id}/read", status_code=204)
async def read_one(notice_id: uuid.UUID, user: CurrentUser, session: Db) -> None:
    await law_changes.mark_read(session, user.id, notice_id)
