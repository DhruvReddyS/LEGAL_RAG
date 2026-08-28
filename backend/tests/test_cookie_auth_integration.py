from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.models import AuditLog, User
from main import app


@pytest.mark.asyncio
async def test_http_only_cookie_login_refresh_and_logout() -> None:
    suffix = uuid.uuid4().hex
    email = f"cookie-{suffix}@example.com"
    user_id: uuid.UUID | None = None
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Origin": "http://localhost:3000"},
        ) as client:
            registered = await client.post(
                "/auth/cookie/register",
                json={
                    "name": "Cookie User",
                    "email": email,
                    "password": "CorrectHorseBattery99!",
                    "role": "citizen",
                },
            )
            assert registered.status_code == 201, registered.text
            user_id = uuid.UUID(registered.json()["id"])
            assert "legal_rag_access" in client.cookies
            assert "legal_rag_refresh" in client.cookies
            assert "HttpOnly" in registered.headers.get_list("set-cookie")[0]

            me = await client.get("/auth/me")
            assert me.status_code == 200
            assert me.json()["email"] == email

            client.cookies.delete("legal_rag_access")
            refreshed = await client.post("/auth/cookie/refresh")
            assert refreshed.status_code == 200, refreshed.text
            assert "legal_rag_access" in client.cookies

            logged_out = await client.post("/auth/cookie/logout")
            assert logged_out.status_code == 204
            assert "legal_rag_access" not in client.cookies
            assert "legal_rag_refresh" not in client.cookies
            assert (await client.get("/auth/me")).status_code == 401
    finally:
        if user_id is not None:
            async with AsyncSessionLocal() as session:
                await session.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()


@pytest.mark.asyncio
async def test_cookie_authentication_rejects_an_untrusted_origin() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/auth/cookie/login",
            headers={"Origin": "https://attacker.example"},
            json={"email": "nobody@example.com", "password": "not-a-real-password"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Untrusted request origin"}
