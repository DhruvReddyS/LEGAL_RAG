"""Case notes, without a database: the rules that must not depend on one."""

from __future__ import annotations

import inspect
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from pydantic import ValidationError

from app.models import AuditLog, Case, CaseNote
from app.routers import case_notes
from app.routers.case_notes import MAX_NOTE_CHARS, CaseNoteWrite
from app.services import privacy

OWNER = SimpleNamespace(id=uuid.uuid4())
STRANGER = SimpleNamespace(id=uuid.uuid4())
SECRET = "The client admitted being there on the 3rd."


class FakeSession:
    """Enough of AsyncSession for the routes, recording what they add."""

    def __init__(self, case_id: uuid.UUID, notes: dict[uuid.UUID, CaseNote] | None = None) -> None:
        self.case = Case(id=case_id, owner_id=OWNER.id)
        self.notes = notes or {}
        self.added: list[object] = []
        self.deleted: list[object] = []

    async def get(self, model, key):
        if model is Case:
            return self.case if key == self.case.id else None
        return self.notes.get(key)

    def add(self, row) -> None:
        if isinstance(row, CaseNote) and row.id is None:
            row.id = uuid.uuid4()
        self.added.append(row)

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...

    async def refresh(self, row) -> None: ...

    async def delete(self, row) -> None:
        self.deleted.append(row)

    def audits(self) -> list[AuditLog]:
        return [row for row in self.added if isinstance(row, AuditLog)]


def test_a_note_is_trimmed_and_cannot_be_blank_or_unbounded() -> None:
    assert CaseNoteWrite(body="  remember the bail date \n").body == "remember the bail date"
    with pytest.raises(ValidationError):
        CaseNoteWrite(body="   \n ")
    with pytest.raises(ValidationError):
        CaseNoteWrite(body="x" * (MAX_NOTE_CHARS + 1))
    assert len(CaseNoteWrite(body="x" * MAX_NOTE_CHARS).body) == MAX_NOTE_CHARS


@pytest.mark.parametrize(
    "call",
    [
        lambda c, s: case_notes.list_notes(c, user=STRANGER, session=s),
        lambda c, s: case_notes.create_note(c, CaseNoteWrite(body=SECRET), user=STRANGER, session=s),
        lambda c, s: case_notes.edit_note(c, uuid.uuid4(), CaseNoteWrite(body=SECRET), user=STRANGER, session=s),
        lambda c, s: case_notes.delete_note(c, uuid.uuid4(), user=STRANGER, session=s),
    ],
)
async def test_every_route_refuses_anyone_but_the_owner(call) -> None:
    case_id = uuid.uuid4()
    with pytest.raises(HTTPException) as refused:
        await call(case_id, FakeSession(case_id))
    assert refused.value.status_code == 403


async def test_an_administrator_is_not_the_owner() -> None:
    # The route takes no role into account, so an admin is just another user.
    source = inspect.getsource(case_notes)
    assert "role" not in source.replace("role_type", "")
    admin = SimpleNamespace(id=uuid.uuid4(), role="admin")
    case_id = uuid.uuid4()
    with pytest.raises(HTTPException) as refused:
        await case_notes.list_notes(case_id, user=admin, session=FakeSession(case_id))
    assert refused.value.status_code == 403


async def test_a_missing_case_is_not_found() -> None:
    with pytest.raises(HTTPException) as missing:
        await case_notes.list_notes(uuid.uuid4(), user=OWNER, session=FakeSession(uuid.uuid4()))
    assert missing.value.status_code == 404


async def test_a_note_from_another_case_is_not_reachable_through_this_one() -> None:
    case_id = uuid.uuid4()
    foreign = CaseNote(id=uuid.uuid4(), case_id=uuid.uuid4(), body=SECRET)
    session = FakeSession(case_id, {foreign.id: foreign})
    for call in (
        case_notes.edit_note(case_id, foreign.id, CaseNoteWrite(body="changed"), user=OWNER, session=session),
        case_notes.delete_note(case_id, foreign.id, user=OWNER, session=session),
    ):
        with pytest.raises(HTTPException) as missing:
            await call
        assert missing.value.status_code == 404
    assert foreign.body == SECRET
    assert session.deleted == []


async def test_no_audit_row_carries_the_note_text() -> None:
    case_id = uuid.uuid4()
    session = FakeSession(case_id)
    created = await case_notes.create_note(case_id, CaseNoteWrite(body=SECRET), user=OWNER, session=session)
    session.notes[created.id] = created
    await case_notes.edit_note(case_id, created.id, CaseNoteWrite(body=f"{SECRET} Again."), user=OWNER, session=session)
    await case_notes.delete_note(case_id, created.id, user=OWNER, session=session)
    audits = session.audits()
    assert [row.action for row in audits] == ["case_note.created", "case_note.edited", "case_note.deleted"]
    for row in audits:
        assert row.metadata_ == {"note_id": str(created.id)}
        assert "admitted" not in f"{row.action}{row.resource_type}{row.metadata_}"
    assert session.deleted == [created]


def test_the_notes_table_goes_with_its_case() -> None:
    column = CaseNote.__table__.c.case_id
    assert [key.ondelete for key in column.foreign_keys] == ["CASCADE"]


def test_the_account_export_includes_notes() -> None:
    source = inspect.getsource(privacy.build_export)
    assert '"case_notes": await rows_for_cases(CaseNote)' in source


def test_the_migration_is_the_single_head() -> None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["f2a8d6c3b915"]
    assert script.get_revision("f2a8d6c3b915").down_revision == "c4f1a7e93b52"
