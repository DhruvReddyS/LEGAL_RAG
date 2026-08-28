from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models import AuditLog, Case, User
from main import app
from tests.helpers import provision_test_user


@pytest.mark.asyncio
async def test_case_workspace_crud_role_derivation_and_cross_user_isolation() -> None:
    suffix = uuid.uuid4().hex
    password = "CorrectHorseBattery99!"
    user_ids: list[uuid.UUID] = []
    case_ids: list[uuid.UUID] = []
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            tokens: dict[str, str] = {}
            for role in ("police", "advocate", "citizen"):
                payload = {
                    "name": f"Case {role}",
                    "email": f"case-{role}-{suffix}@example.com",
                    "password": password,
                    "role": role,
                }
                if role == "citizen":
                    registration = await client.post("/auth/register", json=payload)
                    assert registration.status_code == 201, registration.text
                    body = registration.json()
                else:
                    body = await provision_test_user(**payload)
                tokens[role] = body["access_token"]
                user_ids.append(uuid.UUID(body["user"]["id"]))

            police_headers = {"Authorization": f"Bearer {tokens['police']}"}
            advocate_headers = {"Authorization": f"Bearer {tokens['advocate']}"}
            citizen_headers = {"Authorization": f"Bearer {tokens['citizen']}"}

            citizen_denied = await client.post(
                "/cases", json={"title": "Citizen private matter"}, headers=citizen_headers
            )
            assert citizen_denied.status_code == 403

            mismatched = await client.post(
                "/cases",
                json={"title": "Wrong role", "role_type": "advocate"},
                headers=police_headers,
            )
            assert mismatched.status_code == 403

            created = await client.post(
                "/cases",
                json={"title": "  Missing   property investigation  "},
                headers=police_headers,
            )
            assert created.status_code == 201, created.text
            case = created.json()
            case_ids.append(uuid.UUID(case["id"]))
            assert case["role_type"] == "police"
            assert case["status"] == "open"
            assert case["title"] == "Missing property investigation"

            listed = await client.get("/cases?status=open", headers=police_headers)
            assert listed.status_code == 200
            assert listed.json()["total"] == 1
            assert listed.json()["cases"][0]["id"] == case["id"]

            cross_user_read = await client.get(
                f"/cases/{case['id']}", headers=advocate_headers
            )
            assert cross_user_read.status_code == 403

            updated = await client.patch(
                f"/cases/{case['id']}",
                json={"title": "Missing dog complaint", "status": "archived"},
                headers=police_headers,
            )
            assert updated.status_code == 200, updated.text
            assert updated.json()["title"] == "Missing dog complaint"
            assert updated.json()["status"] == "archived"

            empty_update = await client.patch(
                f"/cases/{case['id']}", json={}, headers=police_headers
            )
            assert empty_update.status_code == 422

            async with AsyncSessionLocal() as session:
                actions = set(
                    (
                        await session.scalars(
                            select(AuditLog.action).where(AuditLog.resource_id == case_ids[0])
                        )
                    ).all()
                )
                assert {"case.create", "case.update"} <= actions
        finally:
            async with AsyncSessionLocal() as session:
                if case_ids:
                    await session.execute(delete(AuditLog).where(AuditLog.resource_id.in_(case_ids)))
                    await session.execute(delete(Case).where(Case.id.in_(case_ids)))
                if user_ids:
                    await session.execute(delete(AuditLog).where(AuditLog.user_id.in_(user_ids)))
                    await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()
