"""The timeline across the API boundary.

The arithmetic is tested next door. What is tested here is what survives
serialisation -- specifically that "we could not determine this" does not
arrive at the client looking like "this is fine", which is the one way a
correct calculation can still mislead the officer reading it.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db_session
from app.core.permissions import POLICE_INVESTIGATION_OWN
from app.core.rbac import PermissionChecker
from app.routers.investigation import router

CHECKER = PermissionChecker(POLICE_INVESTIGATION_OWN, case_id_param="case_id")


class _Session:
    """Collects the audit row without a database behind it."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, item: object) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        return None


def _app() -> tuple[FastAPI, _Session]:
    app = FastAPI()
    app.include_router(router)
    session = _Session()
    app.dependency_overrides[CHECKER] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db_session] = lambda: session
    return app, session


@pytest.mark.asyncio
async def test_the_endpoint_requires_authentication() -> None:
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.post(
            f"/cases/{uuid.uuid4()}/investigation/timeline", json={}
        )

    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_an_undetermined_deadline_arrives_as_null_not_false() -> None:
    """The contract that matters at the boundary.

    `false` reads as "not breached", which is a compliance finding. The
    calculation never made one -- the gravity was not recorded -- and JSON
    is where that distinction is most easily lost, because a bool field
    with a null in it is exactly what a careless client coerces.
    """
    app, _ = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.post(
            f"/cases/{uuid.uuid4()}/investigation/timeline",
            json={"first_remand_at": "2020-01-01T10:00:00+05:30"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    row = next(d for d in body["deadlines"] if d["key"] == "default_bail_entitlement")

    assert row["due_at"] is None
    assert row["is_breached"] is None
    assert "gravity" in row["undetermined_because"]
    # Listed as undetermined, and specifically not listed as breached: an
    # unknown must not be filed under either heading.
    assert "default_bail_entitlement" in body["undetermined"]
    assert "default_bail_entitlement" not in body["breached"]


@pytest.mark.asyncio
async def test_a_computed_deadline_carries_its_provision() -> None:
    app, _ = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.post(
            f"/cases/{uuid.uuid4()}/investigation/timeline",
            json={
                "first_remand_at": "2026-01-03T10:00:00+05:30",
                "gravity": "death_life_or_ten_years_or_more",
            },
        )

    row = next(
        d for d in response.json()["deadlines"] if d["key"] == "default_bail_entitlement"
    )

    assert row["provision"] == "BNSS s.187(3)(i)"
    assert row["due_at"].startswith("2026-04-03")
    assert "first remand" in row["computed_from"]


@pytest.mark.asyncio
async def test_the_request_is_audited() -> None:
    """Someone computed a custody deadline on this matter; that is a fact
    about the case and belongs in the audit log like any other access."""
    app, session = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await client.post(
            f"/cases/{uuid.uuid4()}/investigation/timeline",
            json={"arrested_at": "2026-01-01T10:00:00+05:30"},
        )

    assert len(session.added) == 1
    assert session.added[0].action == "police.investigation_timeline"


@pytest.mark.asyncio
async def test_no_facts_returns_no_deadlines_rather_than_a_default_schedule() -> None:
    app, _ = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.post(
            f"/cases/{uuid.uuid4()}/investigation/timeline", json={}
        )

    assert response.json()["deadlines"] == []
