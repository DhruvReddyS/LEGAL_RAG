"""Input a person can really produce must get an answer, not a 500.

A pasted NUL character reached PostgreSQL from any text field. A year of 9999 was stored
and then broke that case's timeline, register and case file on every later read. A very
long filename overflowed its column. A future date on a witness was simply recorded.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.routers.advocate_tools import get_advocate_runtime
from app.models import AuditLog, Case, InvestigationFacts as FactsRow, StorageObject, User
from main import app
from tests.helpers import provision_test_user, unique_email


async def _account(role: str) -> SimpleNamespace:
    body = await provision_test_user(
        name="Awkward Input", email=unique_email(f"awkward-{role}"), password="CorrectHorseBattery99!", role=role
    )
    return SimpleNamespace(
        id=uuid.UUID(body["user"]["id"]), headers={"Authorization": f"Bearer {body['access_token']}"}
    )


@pytest_asyncio.fixture(loop_scope="session")
async def world():
    officer, advocate = await _account("police"), await _account("advocate")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        made = await client.post("/cases", json={"title": "Awkward"}, headers=officer.headers)
        matter = await client.post("/cases", json={"title": "Awkward"}, headers=advocate.headers)
        yield SimpleNamespace(
            client=client,
            officer=officer,
            advocate=advocate,
            case=made.json()["id"],
            matter=matter.json()["id"],
        )
    async with AsyncSessionLocal() as session:
        for case_id in (made.json()["id"], matter.json()["id"]):
            await session.execute(delete(FactsRow).where(FactsRow.case_id == uuid.UUID(case_id)))
            await session.execute(delete(StorageObject).where(StorageObject.case_id == uuid.UUID(case_id)))
            await session.execute(delete(Case).where(Case.id == uuid.UUID(case_id)))
        for user in (officer.id, advocate.id):
            await session.execute(delete(AuditLog).where(AuditLog.user_id == user))
            await session.execute(delete(User).where(User.id == user))
        await session.commit()


@pytest.mark.asyncio
async def test_a_nul_character_is_refused_in_words_wherever_it_is_typed(world) -> None:
    headers = world.officer.headers
    base = f"/cases/{world.case}"
    for path, body in (
        (f"{base}/notes", {"body": "a\u0000b"}),
        (f"{base}/police/witnesses", {"name": "a\u0000b"}),
        (f"{base}/police/searches", {"place": "a\u0000b"}),
        (f"{base}/police/diary", {"entry_date": "2026-11-02", "circumstances": "a\u0000b"}),
        ("/cases", {"title": "a\u0000b"}),
    ):
        response = await world.client.post(path, json=body, headers=headers)
        assert response.status_code == 422, f"{path}: {response.status_code} {response.text}"
        assert "cannot be stored" in response.json()["detail"]
    # The session that failed did not poison the next request.
    assert (await world.client.get(f"{base}/notes", headers=headers)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("moment", ["9999-12-31T23:59:59+00:00", "0001-01-01T00:00:00+00:00"])
async def test_a_date_no_one_could_mean_is_refused_before_it_can_break_later_reads(world, moment) -> None:
    headers = world.officer.headers
    base = f"/cases/{world.case}"
    refused = await world.client.put(
        f"{base}/investigation/facts", json={"information_recorded_at": moment, "gravity": "other"}, headers=headers
    )
    assert refused.status_code == 422, refused.text
    for path in (f"{base}/investigation/timeline", f"{base}/police/case-file", "/police/deadlines"):
        assert (await world.client.get(path, headers=headers)).status_code < 500, path


@pytest.mark.asyncio
async def test_advocate_date_tools_refuse_a_date_that_would_overflow(world) -> None:
    app.dependency_overrides[get_advocate_runtime] = lambda: SimpleNamespace()
    headers = world.advocate.headers
    tools = f"/cases/{world.matter}/advocate"
    articles = (await world.client.get("/advocate/limitation-articles", headers=headers)).json()["articles"]
    limitation = await world.client.post(
        f"{tools}/calendar/limitation",
        json={"article": articles[0]["key"], "runs_from": "9999-12-31"},
        headers=headers,
    )
    assert limitation.status_code == 422
    bail = await world.client.post(
        f"{tools}/bail/assess",
        json={"routes": ["default"], "first_remand_on": "9999-12-31", "gravity": "other", "in_custody": True},
        headers=headers,
    )
    assert bail.status_code == 422
    calendar = await world.client.post(
        f"{tools}/calendar", json={"kind": "hearing", "title": "x", "due_on": "0001-01-01"}, headers=headers
    )
    assert calendar.status_code == 422
    app.dependency_overrides.pop(get_advocate_runtime, None)


@pytest.mark.asyncio
async def test_a_witness_statement_cannot_be_dated_in_the_future(world) -> None:
    headers = world.officer.headers
    witnesses = f"/cases/{world.case}/police/witnesses"
    created = await world.client.post(
        witnesses, json={"name": "Ann", "statement_recorded_at": "2099-01-01T00:00:00+00:00"}, headers=headers
    )
    assert created.status_code == 422
    made = await world.client.post(witnesses, json={"name": "Ann"}, headers=headers)
    assert made.status_code == 201
    for field in ("statement_recorded_at", "magistrate_statement_at", "bond_executed_at"):
        patched = await world.client.patch(
            f"{witnesses}/{made.json()['id']}", json={field: "2099-01-01T00:00:00+00:00"}, headers=headers
        )
        assert patched.status_code == 422, field


@pytest.mark.asyncio
async def test_a_very_long_filename_is_stored_cut_short_not_refused_with_a_500(world) -> None:
    uploaded = await world.client.post(
        f"/cases/{world.case}/storage/objects",
        files={"file": ("x" * 2000 + ".txt", b"hello", "text/plain")},
        headers=world.officer.headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    assert len(uploaded.json()["original_filename"]) <= 500
    assert uploaded.json()["original_filename"].endswith(".txt")
