"""Recorded facts, and what must survive the round trip.

The arithmetic is tested against the Sanhita elsewhere. What is tested here
is the database: specifically that "we did not record this" comes back as
itself, and not as a plausible default that produces a confident deadline.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration

PASSWORD = "RedTeam-Password-9142"


async def _client() -> AsyncClient:
    from main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _police_case() -> tuple[dict[str, str], uuid.UUID]:
    body = await provision_test_user(
        name="Timeline Officer",
        email=unique_email("timeline-officer"),
        password=PASSWORD,
        role="police",
    )
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    async with await _client() as client:
        created = await client.post(
            "/cases", json={"title": "Timeline matter"}, headers=headers
        )
        assert created.status_code == 201, created.text
    return headers, uuid.UUID(created.json()["id"])


@pytest.mark.asyncio
async def test_unknown_gravity_survives_the_round_trip() -> None:
    """The property the whole column exists for.

    A default of 'other' in the database would give every unrecorded
    offence a sixty-day s.187(3) deadline -- a confident date derived from
    an absence, and the one that hides a default-bail entitlement that has
    already accrued.
    """
    headers, case_id = await _police_case()
    async with await _client() as client:
        stored = await client.put(
            f"/cases/{case_id}/investigation/facts",
            json={"first_remand_at": "2026-01-03T10:00:00+05:30"},
            headers=headers,
        )
        assert stored.status_code == 200, stored.text
        assert stored.json()["gravity"] == "unknown"

        timeline = await client.get(
            f"/cases/{case_id}/investigation/timeline", headers=headers
        )

    row = next(
        d
        for d in timeline.json()["deadlines"]
        if d["key"] == "default_bail_entitlement"
    )
    assert row["due_at"] is None
    assert row["is_breached"] is None
    assert "gravity" in row["undetermined_because"]


@pytest.mark.asyncio
async def test_recording_facts_twice_updates_rather_than_duplicates() -> None:
    """Two rows would mean two answers to "when was the accused remanded",
    and the arithmetic would use whichever came back first."""
    headers, case_id = await _police_case()
    async with await _client() as client:
        for remand in ("2026-01-03T10:00:00+05:30", "2026-01-05T10:00:00+05:30"):
            response = await client.put(
                f"/cases/{case_id}/investigation/facts",
                json={"first_remand_at": remand, "gravity": "other"},
                headers=headers,
            )
            assert response.status_code == 200, response.text

        current = await client.get(
            f"/cases/{case_id}/investigation/facts", headers=headers
        )

    assert current.json()["first_remand_at"].startswith("2026-01-05")


@pytest.mark.asyncio
async def test_a_wrongly_entered_date_can_be_cleared() -> None:
    """The reason this is a replace and not a merge.

    Under merge semantics a null is indistinguishable from an omitted
    field, so a mistyped arrest time could never be removed -- it would
    stay on record and keep generating a production deadline for an arrest
    that never happened.
    """
    headers, case_id = await _police_case()
    async with await _client() as client:
        await client.put(
            f"/cases/{case_id}/investigation/facts",
            json={"arrested_at": "2026-01-01T10:00:00+05:30"},
            headers=headers,
        )
        cleared = await client.put(
            f"/cases/{case_id}/investigation/facts", json={}, headers=headers
        )
        assert cleared.json()["arrested_at"] is None

        timeline = await client.get(
            f"/cases/{case_id}/investigation/timeline", headers=headers
        )

    assert timeline.json()["deadlines"] == []


@pytest.mark.asyncio
async def test_nothing_recorded_is_a_404_not_an_empty_schedule() -> None:
    """An empty schedule reads as "no deadlines apply to this matter".

    That is a finding. "Nothing has been recorded yet" is not, and the two
    must not arrive looking the same.
    """
    headers, case_id = await _police_case()
    async with await _client() as client:
        timeline = await client.get(
            f"/cases/{case_id}/investigation/timeline", headers=headers
        )
        facts = await client.get(
            f"/cases/{case_id}/investigation/facts", headers=headers
        )

    assert timeline.status_code == 404
    assert facts.status_code == 404


@pytest.mark.asyncio
async def test_another_officer_cannot_read_or_write_this_matter() -> None:
    """Case isolation covers the new endpoints, not only the old ones."""
    headers, case_id = await _police_case()
    intruder = await provision_test_user(
        name="Other Officer",
        email=unique_email("other-officer"),
        password=PASSWORD,
        role="police",
    )
    other = {"Authorization": f"Bearer {intruder['access_token']}"}

    async with await _client() as client:
        await client.put(
            f"/cases/{case_id}/investigation/facts",
            json={"arrested_at": "2026-01-01T10:00:00+05:30"},
            headers=headers,
        )
        wrote = await client.put(
            f"/cases/{case_id}/investigation/facts",
            json={"arrested_at": "2020-01-01T10:00:00+05:30"},
            headers=other,
        )
        read = await client.get(
            f"/cases/{case_id}/investigation/facts", headers=other
        )
        timeline = await client.get(
            f"/cases/{case_id}/investigation/timeline", headers=other
        )

    assert wrote.status_code == 403
    assert read.status_code == 403
    assert timeline.status_code == 403


@pytest.mark.asyncio
async def test_a_citizen_cannot_reach_the_investigation_endpoints() -> None:
    citizen = await provision_test_user(
        name="Curious Citizen",
        email=unique_email("curious-citizen"),
        password=PASSWORD,
        role="citizen",
    )
    headers = {"Authorization": f"Bearer {citizen['access_token']}"}

    async with await _client() as client:
        response = await client.get(
            f"/cases/{uuid.uuid4()}/investigation/timeline", headers=headers
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_the_column_itself_defaults_to_unknown() -> None:
    """Not only the request schema.

    The API path always sends a gravity, because the request schema
    supplies "unknown" when the caller omits it -- so a wrong database
    default would never show up through the endpoint. A row written by
    anything else (a fixture, a backfill, a later code path) would get it,
    and would then carry a sixty-day s.187(3) deadline nobody chose.
    """
    _, case_id = await _police_case()

    # Raw INSERT naming no gravity, so the value comes from the column's own
    # DEFAULT rather than from anything in Python.
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "INSERT INTO investigation_facts (id, case_id) "
                "VALUES (:id, :case_id)"
            ),
            {"id": uuid.uuid4(), "case_id": case_id},
        )
        await session.commit()
        stored = await session.scalar(
            text("SELECT gravity FROM investigation_facts WHERE case_id = :case_id"),
            {"case_id": case_id},
        )

    assert stored == "unknown"


@pytest.mark.asyncio
async def test_the_request_schema_also_defaults_to_unknown() -> None:
    """The other half of the same guarantee, on the path callers use."""
    headers, case_id = await _police_case()
    async with await _client() as client:
        response = await client.put(
            f"/cases/{case_id}/investigation/facts",
            json={"arrested_at": "2026-01-01T10:00:00+05:30"},
            headers=headers,
        )

    assert response.json()["gravity"] == "unknown"
