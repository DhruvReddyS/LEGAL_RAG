from __future__ import annotations

import uuid

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.core.permissions import CASE_EDIT_OWN
from app.core.rbac import require_permission
from app.models import AuditLog, Case, User
from app.models.enums import CaseRoleType
from main import app
from tests.helpers import provision_test_user


@app.get("/_tests/cases/{case_id}/edit")
async def rbac_probe(
    current_user: User = Depends(require_permission(CASE_EDIT_OWN)),
) -> dict[str, str]:
    return {"user_id": str(current_user.id)}


@pytest.mark.asyncio
async def test_authentication_and_case_ownership_rbac() -> None:
    suffix = uuid.uuid4().hex
    password = "CorrectHorseBattery99!"
    registrations = [
        {
            "name": "Police Owner",
            "email": f"police-owner-{suffix}@example.com",
            "password": password,
            "role": "police",
        },
        {
            "name": "Police Other",
            "email": f"police-other-{suffix}@example.com",
            "password": password,
            "role": "police",
        },
        {
            "name": "Citizen User",
            "email": f"citizen-{suffix}@example.com",
            "password": password,
            "role": "citizen",
        },
    ]
    created_user_ids: list[uuid.UUID] = []
    created_case_ids: list[uuid.UUID] = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            auth_responses = []
            for registration in registrations:
                if registration["role"] == "citizen":
                    response = await client.post("/auth/register", json=registration)
                    assert response.status_code == 201, response.text
                    body = response.json()
                else:
                    body = await provision_test_user(**registration)
                assert body["access_token"]
                assert body["refresh_token"]
                assert body["user"]["email"] == registration["email"]
                created_user_ids.append(uuid.UUID(body["user"]["id"]))
                auth_responses.append(body)

            duplicate = await client.post("/auth/register", json=registrations[2])
            assert duplicate.status_code == 409

            admin_registration = await client.post(
                "/auth/register",
                json={**registrations[2], "email": f"admin-{suffix}@example.com", "role": "admin"},
            )
            assert admin_registration.status_code == 422

            professional_self_registration = await client.post(
                "/auth/register",
                json={**registrations[0], "email": f"self-police-{suffix}@example.com"},
            )
            assert professional_self_registration.status_code == 403

            login = await client.post(
                "/auth/login",
                json={"email": registrations[0]["email"], "password": password},
            )
            assert login.status_code == 200, login.text
            owner_tokens = login.json()

            wrong_password = await client.post(
                "/auth/login",
                json={"email": registrations[0]["email"], "password": "incorrect-password"},
            )
            assert wrong_password.status_code == 401

            me = await client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {owner_tokens['access_token']}"},
            )
            assert me.status_code == 200
            assert me.json()["id"] == str(created_user_ids[0])

            refresh = await client.post(
                "/auth/refresh",
                json={"refresh_token": owner_tokens["refresh_token"]},
            )
            assert refresh.status_code == 200, refresh.text
            assert refresh.json()["access_token"] != owner_tokens["access_token"]

            refresh_as_access = await client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {owner_tokens['refresh_token']}"},
            )
            assert refresh_as_access.status_code == 401

            async with AsyncSessionLocal() as session:
                owner_case = Case(
                    owner_id=created_user_ids[0],
                    role_type=CaseRoleType.POLICE,
                    title="Owner case",
                    status="open",
                )
                other_case = Case(
                    owner_id=created_user_ids[1],
                    role_type=CaseRoleType.POLICE,
                    title="Other officer case",
                    status="open",
                )
                mismatched_case = Case(
                    owner_id=created_user_ids[0],
                    role_type=CaseRoleType.ADVOCATE,
                    title="Mismatched role case",
                    status="open",
                )
                session.add_all([owner_case, other_case, mismatched_case])
                await session.commit()
                created_case_ids.extend([owner_case.id, other_case.id, mismatched_case.id])

                stored_hash = await session.scalar(
                    select(User.hashed_password).where(User.id == created_user_ids[0])
                )
                assert stored_hash is not None
                assert stored_hash != password
                assert stored_hash.startswith("$2")

            owner_access = await client.get(
                f"/_tests/cases/{created_case_ids[0]}/edit",
                headers={"Authorization": f"Bearer {owner_tokens['access_token']}"},
            )
            assert owner_access.status_code == 200

            other_case_denied = await client.get(
                f"/_tests/cases/{created_case_ids[1]}/edit",
                headers={"Authorization": f"Bearer {owner_tokens['access_token']}"},
            )
            assert other_case_denied.status_code == 403

            role_mismatch_denied = await client.get(
                f"/_tests/cases/{created_case_ids[2]}/edit",
                headers={"Authorization": f"Bearer {owner_tokens['access_token']}"},
            )
            assert role_mismatch_denied.status_code == 403

            citizen_denied = await client.get(
                f"/_tests/cases/{created_case_ids[0]}/edit",
                headers={
                    "Authorization": f"Bearer {auth_responses[2]['access_token']}"
                },
            )
            assert citizen_denied.status_code == 403
        finally:
            async with AsyncSessionLocal() as session:
                if created_case_ids:
                    await session.execute(delete(Case).where(Case.id.in_(created_case_ids)))
                if created_user_ids:
                    await session.execute(
                        delete(AuditLog).where(AuditLog.resource_id.in_(created_user_ids))
                    )
                    await session.execute(delete(User).where(User.id.in_(created_user_ids)))
                await session.commit()
