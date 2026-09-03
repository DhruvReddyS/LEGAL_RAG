"""Rotation, reuse detection and logout revocation.

Before this, a refresh token was valid for its full seven days no matter what.
Rotation issued a new pair without invalidating the old one, and logout only
cleared a cookie - an instruction to one browser, not a revocation. A token
copied off a shared machine kept working for a week, and nobody could end it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import AsyncSessionLocal
from app.models import RevokedRefreshToken, User
from app.services import token_revocation
from tests.helpers import provision_test_user, unique_email


pytestmark = pytest.mark.integration


async def _client() -> AsyncClient:
    from main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_rotation_revokes_the_token_it_consumed() -> None:
    account = await provision_test_user(
        name="Rotate One",
        email=unique_email("rotate-one"),
        password="Rotate-One-Password-1",
        role="citizen",
    )

    async with await _client() as client:
        first = await client.post(
            "/auth/refresh", json={"refresh_token": account["refresh_token"]}
        )
        assert first.status_code == 200
        rotated = first.json()["refresh_token"]
        assert rotated != account["refresh_token"]

        # The consumed token is dead; the new one works.
        replayed = await client.post(
            "/auth/refresh", json={"refresh_token": account["refresh_token"]}
        )
        assert replayed.status_code == 401


async def test_replaying_a_consumed_token_ends_every_session() -> None:
    """A replay is evidence of compromise, not a retry.

    Refusing only the replayed call would leave whichever party holds the newer
    token signed in - which, if the replay came from the legitimate user, is
    the attacker.
    """
    account = await provision_test_user(
        name="Reuse Detect",
        email=unique_email("reuse-detect"),
        password="Reuse-Detect-Password-1",
        role="citizen",
    )

    async with await _client() as client:
        rotated = (
            await client.post(
                "/auth/refresh", json={"refresh_token": account["refresh_token"]}
            )
        ).json()["refresh_token"]

        replay = await client.post(
            "/auth/refresh", json={"refresh_token": account["refresh_token"]}
        )
        assert replay.status_code == 401

        # The token issued by the rotation is now dead too.
        assert (
            await client.post("/auth/refresh", json={"refresh_token": rotated})
        ).status_code == 401

        # And so is the access token that was already in flight.
        assert (
            await client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {account['access_token']}"},
            )
        ).status_code == 401


async def test_logout_revokes_server_side_not_just_the_cookie() -> None:
    async with await _client() as client:
        # Cookie flows require a trusted Origin: DesktopOriginSecurityMiddleware
        # refuses a credentialed mutation without one, which is the CSRF
        # defence CORS alone does not provide.
        origin = {"Origin": "http://test"}
        registration = await client.post(
            "/auth/cookie/register",
            headers=origin,
            json={
                "name": "Logout Revoke",
                "email": unique_email("logout-revoke"),
                "password": "Logout-Revoke-Password-1",
            },
        )
        assert registration.status_code == 201
        stolen = client.cookies.get("legal_rag_refresh")
        assert stolen

        assert (await client.post("/auth/cookie/logout", headers=origin)).status_code == 204

        # A copy taken before sign-out must no longer work.
        assert (
            await client.post("/auth/refresh", json={"refresh_token": stolen})
        ).status_code == 401


async def test_revocation_is_idempotent_for_a_retried_request() -> None:
    """A dropped connection makes a client retry; that must not raise."""
    account = await provision_test_user(
        name="Idempotent",
        email=unique_email("idempotent-revoke"),
        password="Idempotent-Password-1",
        role="citizen",
    )
    jti = uuid.uuid4()
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    async with AsyncSessionLocal() as session:
        user_id = uuid.UUID(account["user"]["id"])
        for _ in range(2):
            await token_revocation.revoke(
                session,
                jti=jti,
                user_id=user_id,
                expires_at=expires,
                reason=token_revocation.REASON_LOGOUT,
            )
        await session.commit()
        assert await token_revocation.is_revoked(session, jti) is True


async def test_expired_revocations_are_purged() -> None:
    """The table would otherwise grow for the life of the deployment."""
    account = await provision_test_user(
        name="Purge",
        email=unique_email("purge-revocations"),
        password="Purge-Password-1",
        role="citizen",
    )
    user_id = uuid.UUID(account["user"]["id"])

    async with AsyncSessionLocal() as session:
        await token_revocation.revoke(
            session,
            jti=uuid.uuid4(),
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            reason=token_revocation.REASON_ROTATED,
        )
        live = uuid.uuid4()
        await token_revocation.revoke(
            session,
            jti=live,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            reason=token_revocation.REASON_ROTATED,
        )
        await session.commit()

        assert await token_revocation.purge_expired(session) >= 1
        await session.commit()
        # A revocation that still matters survives the sweep.
        assert await token_revocation.is_revoked(session, live) is True
