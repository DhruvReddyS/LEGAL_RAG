"""The authority check across the API boundary.

The service is tested against the concordance next door. What matters here
is that both drafting roles can reach it, that nobody else can reach their
matter, and that the draft itself never lands in the audit log.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from tests.helpers import provision_test_user, unique_email

pytestmark = pytest.mark.integration

PASSWORD = "RedTeam-Password-9142"

DRAFT = (
    "The applicant seeks relief under section 438 of the Code of Criminal "
    "Procedure. The prosecution has invoked section 124A of the Indian Penal "
    "Code. Article 21 of the Constitution is also engaged."
)


async def _client() -> AsyncClient:
    from main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _case_for(role: str) -> tuple[dict[str, str], uuid.UUID]:
    body = await provision_test_user(
        name=f"Authority {role}",
        email=unique_email(f"authority-{role}"),
        password=PASSWORD,
        role=role,
    )
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    async with await _client() as client:
        created = await client.post(
            "/cases", json={"title": f"Authority {role} matter"}, headers=headers
        )
        assert created.status_code == 201, created.text
    return headers, uuid.UUID(created.json()["id"])


@pytest.mark.parametrize("role", ["advocate", "police"])
@pytest.mark.asyncio
async def test_both_drafting_roles_can_check_a_draft(role: str) -> None:
    """An FIR citing IPC numbers has the same problem as a petition citing
    CrPC ones, so this is not advocate-only."""
    headers, case_id = await _case_for(role)
    async with await _client() as client:
        response = await client.post(
            f"/cases/{case_id}/authorities/check",
            json={"draft": DRAFT},
            headers=headers,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    by_citation = {row["citation"]: row for row in body["checked"]}
    assert by_citation["IPC s.124A"]["finding"] == "not_re_enacted"
    assert "BNSS s.482" in by_citation["CrPC s.438"]["successors"]
    assert body["not_re_enacted"] == 1


@pytest.mark.asyncio
async def test_a_citation_outside_the_concordance_is_counted_not_hidden() -> None:
    """The count tells the reader the check was partial.

    Without it, a report listing three rows implies three citations were
    verified, when one of them was only recognised.
    """
    headers, case_id = await _case_for("advocate")
    async with await _client() as client:
        response = await client.post(
            f"/cases/{case_id}/authorities/check",
            json={"draft": DRAFT},
            headers=headers,
        )

    body = response.json()
    assert body["not_checked"] == 1
    constitution = next(r for r in body["checked"] if r["code"] == "Constitution")
    assert constitution["needs_attention"] is False


@pytest.mark.asyncio
async def test_the_draft_is_never_written_to_the_audit_log() -> None:
    """It is privileged work product.

    The log answers who checked what and when. Recording the petition text
    would make the audit trail a copy of every draft on the system.
    """
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models import AuditLog

    headers, case_id = await _case_for("advocate")
    secret = "the client admits presence at the scene"
    async with await _client() as client:
        await client.post(
            f"/cases/{case_id}/authorities/check",
            json={"draft": f"{DRAFT} {secret}"},
            headers=headers,
        )

    async with AsyncSessionLocal() as session:
        rows = (
            await session.scalars(
                select(AuditLog).where(AuditLog.resource_id == case_id)
            )
        ).all()

    assert rows
    for row in rows:
        assert secret not in str(row.metadata_)


@pytest.mark.asyncio
async def test_another_owner_cannot_check_against_this_matter() -> None:
    headers, case_id = await _case_for("advocate")
    intruder = await provision_test_user(
        name="Other Advocate",
        email=unique_email("other-advocate"),
        password=PASSWORD,
        role="advocate",
    )
    async with await _client() as client:
        response = await client.post(
            f"/cases/{case_id}/authorities/check",
            json={"draft": DRAFT},
            headers={"Authorization": f"Bearer {intruder['access_token']}"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_empty_draft_is_rejected_rather_than_silently_clean() -> None:
    """A response of "nothing needs attention" to an empty draft reads as a
    clean bill of health."""
    headers, case_id = await _case_for("advocate")
    async with await _client() as client:
        response = await client.post(
            f"/cases/{case_id}/authorities/check", json={"draft": ""}, headers=headers
        )

    assert response.status_code == 422
