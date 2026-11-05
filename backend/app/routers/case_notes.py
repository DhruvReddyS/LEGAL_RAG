"""A case owner's private notes. Nobody else reads them, administrators included."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.permissions import CASE_EDIT_OWN, CASE_READ_OWN
from app.core.rbac import require_permission
from app.models import AuditLog, Case, CaseNote, User

router = APIRouter(tags=["case-notes"])

MAX_NOTE_CHARS = 10_000
NoteBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_NOTE_CHARS)]


class CaseNoteWrite(BaseModel):
    body: NoteBody


class CaseNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    body: str
    created_at: datetime
    updated_at: datetime


class CaseNoteList(BaseModel):
    notes: list[CaseNoteResponse] = Field(default_factory=list)


async def _owned_case(session: AsyncSession, case_id: uuid.UUID, user: User) -> Case:
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    # The owner only, with no administrator exception, as for the chronology.
    if case.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not own this case")
    return case


async def _note_in_case(session: AsyncSession, case_id: uuid.UUID, note_id: uuid.UUID) -> CaseNote:
    note = await session.get(CaseNote, note_id)
    # Through this case only: a note id from another case is simply not here.
    if note is None or note.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    return note


def _audit(session: AsyncSession, user: User, action: str, case_id: uuid.UUID, note_id: uuid.UUID) -> None:
    # That a note changed, and never what it says.
    session.add(
        AuditLog(
            user_id=user.id,
            action=f"case_note.{action}",
            resource_type="case",
            resource_id=case_id,
            metadata_={"note_id": str(note_id)},
        )
    )


@router.get("/cases/{case_id}/notes", response_model=CaseNoteList)
async def list_notes(
    case_id: uuid.UUID,
    user: User = Depends(require_permission(CASE_READ_OWN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await _owned_case(session, case_id, user)
    rows = await session.scalars(
        select(CaseNote)
        .where(CaseNote.case_id == case_id)
        .order_by(CaseNote.created_at.desc(), CaseNote.id.desc())
    )
    return {"notes": list(rows.all())}


@router.post("/cases/{case_id}/notes", response_model=CaseNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    case_id: uuid.UUID,
    request: CaseNoteWrite,
    user: User = Depends(require_permission(CASE_EDIT_OWN)),
    session: AsyncSession = Depends(get_db_session),
) -> CaseNote:
    await _owned_case(session, case_id, user)
    note = CaseNote(case_id=case_id, body=request.body)
    session.add(note)
    await session.flush()
    _audit(session, user, "created", case_id, note.id)
    await session.commit()
    await session.refresh(note)
    return note


@router.put("/cases/{case_id}/notes/{note_id}", response_model=CaseNoteResponse)
async def edit_note(
    case_id: uuid.UUID,
    note_id: uuid.UUID,
    request: CaseNoteWrite,
    user: User = Depends(require_permission(CASE_EDIT_OWN)),
    session: AsyncSession = Depends(get_db_session),
) -> CaseNote:
    await _owned_case(session, case_id, user)
    note = await _note_in_case(session, case_id, note_id)
    note.body = request.body
    _audit(session, user, "edited", case_id, note.id)
    await session.commit()
    await session.refresh(note)
    return note


@router.delete("/cases/{case_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    case_id: uuid.UUID,
    note_id: uuid.UUID,
    user: User = Depends(require_permission(CASE_EDIT_OWN)),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await _owned_case(session, case_id, user)
    note = await _note_in_case(session, case_id, note_id)
    _audit(session, user, "deleted", case_id, note.id)
    await session.delete(note)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
