"""Case notes against PostgreSQL. Marked for the integration run, not the unit run."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import cast, func, select, String

from app.core.database import AsyncSessionLocal
from app.models import AuditLog, Case, CaseNote, User
from app.services import privacy
from main import app
from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration

PASSWORD = "Case-notes-Pass-123!"
SECRET = "Privately: the second witness seems unreliable."


def _bearer(account: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {account['access_token']}"}


async def _account(role: str, prefix: str) -> dict:
    return await provision_test_user(name="Note Taker", email=unique_email(prefix), password=PASSWORD, role=role)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _case(client: AsyncClient, owner: dict) -> str:
    created = await client.post("/cases", json={"title": "Notes matter"}, headers=_bearer(owner))
    assert created.status_code in {200, 201}, created.text
    return created.json()["id"]


async def test_the_owner_creates_edits_lists_newest_first_and_deletes() -> None:
    owner = await _account("advocate", "notes-owner")
    async with _client() as client:
        case_id = await _case(client, owner)
        first = await client.post(f"/cases/{case_id}/notes", json={"body": "first"}, headers=_bearer(owner))
        assert first.status_code == 201, first.text
        second = await client.post(f"/cases/{case_id}/notes", json={"body": "second"}, headers=_bearer(owner))
        assert second.status_code == 201, second.text

        listed = await client.get(f"/cases/{case_id}/notes", headers=_bearer(owner))
        assert [note["body"] for note in listed.json()["notes"]] == ["second", "first"]

        note_id = first.json()["id"]
        edited = await client.put(f"/cases/{case_id}/notes/{note_id}", json={"body": "first, edited"}, headers=_bearer(owner))
        assert edited.status_code == 200, edited.text
        assert edited.json()["body"] == "first, edited"

        blank = await client.post(f"/cases/{case_id}/notes", json={"body": "   "}, headers=_bearer(owner))
        assert blank.status_code == 422

        removed = await client.delete(f"/cases/{case_id}/notes/{note_id}", headers=_bearer(owner))
        assert removed.status_code == 204
        listed = await client.get(f"/cases/{case_id}/notes", headers=_bearer(owner))
        assert [note["body"] for note in listed.json()["notes"]] == ["second"]


@pytest.mark.parametrize("role", ["advocate", "police", "admin"])
async def test_nobody_else_reads_or_changes_a_note(role: str) -> None:
    owner = await _account("advocate", "notes-owner")
    other = await _account(role, f"notes-{role}")
    async with _client() as client:
        case_id = await _case(client, owner)
        note = await client.post(f"/cases/{case_id}/notes", json={"body": SECRET}, headers=_bearer(owner))
        note_id = note.json()["id"]
        headers = _bearer(other)
        refused = [
            await client.get(f"/cases/{case_id}/notes", headers=headers),
            await client.post(f"/cases/{case_id}/notes", json={"body": "x"}, headers=headers),
            await client.put(f"/cases/{case_id}/notes/{note_id}", json={"body": "x"}, headers=headers),
            await client.delete(f"/cases/{case_id}/notes/{note_id}", headers=headers),
        ]
        for response in refused:
            assert response.status_code in {403, 404}, response.text
            assert SECRET not in response.text


async def test_the_text_stays_out_of_the_audit_log_and_in_the_export() -> None:
    owner = await _account("advocate", "notes-audit")
    async with _client() as client:
        case_id = await _case(client, owner)
        created = await client.post(f"/cases/{case_id}/notes", json={"body": SECRET}, headers=_bearer(owner))
        assert created.status_code == 201
    async with AsyncSessionLocal() as session:
        leaked = await session.scalar(
            select(func.count()).select_from(AuditLog).where(cast(AuditLog.metadata_, String).contains("unreliable"))
        )
        assert leaked == 0
        user = await session.get(User, uuid.UUID(owner["user"]["id"]))
        exported = await privacy.build_export(session, user)
    assert [row["body"] for row in exported["case_notes"]] == [SECRET]


async def test_removing_the_case_removes_its_notes() -> None:
    owner = await _account("advocate", "notes-erase")
    async with _client() as client:
        case_id = await _case(client, owner)
        await client.post(f"/cases/{case_id}/notes", json={"body": SECRET}, headers=_bearer(owner))
    async with AsyncSessionLocal() as session:
        case = await session.get(Case, uuid.UUID(case_id))
        await session.delete(case)
        await session.commit()
        count = await session.scalar(
            select(func.count()).select_from(CaseNote).where(CaseNote.case_id == uuid.UUID(case_id))
        )
    assert count == 0
