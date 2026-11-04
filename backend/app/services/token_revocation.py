"""Refresh-token rotation with reuse detection.

Rotation alone is not enough. If the old token stays valid after a new pair is
issued, a stolen token is as good as a live session. If the old token is simply
rejected, a theft looks identical to a network retry and nobody learns of it.

The standard resolution is rotation plus reuse detection: each refresh revokes
the token it consumed, and presenting an already-revoked token is treated as
evidence of compromise, which revokes the whole family rather than just the one
token. That last step is what turns a stolen token into a session that ends
instead of a session that continues.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, RevokedRefreshToken, User, UserSession


REASON_ROTATED = "rotated"
REASON_LOGOUT = "logout"
REASON_REUSE_DETECTED = "reuse_detected"


async def is_revoked(session: AsyncSession, jti: uuid.UUID) -> bool:
    return (
        await session.scalar(
            select(RevokedRefreshToken.jti).where(RevokedRefreshToken.jti == jti)
        )
    ) is not None


async def rotated_within(
    session: AsyncSession, jti: uuid.UUID, *, seconds: int
) -> bool:
    """Whether this token was rotated moments ago, by another tab's refresh.

    Only rotation qualifies. A token ended by logout or by reuse detection has
    no innocent second use.
    """
    if seconds <= 0:
        return False
    row = await session.get(RevokedRefreshToken, jti, populate_existing=True)
    if row is None or row.reason != REASON_ROTATED:
        return False
    return row.revoked_at >= datetime.now(timezone.utc) - timedelta(seconds=seconds)


async def revoke(
    session: AsyncSession,
    *,
    jti: uuid.UUID,
    user_id: uuid.UUID,
    expires_at: datetime,
    reason: str,
) -> bool:
    """Record one token as unusable. True if this call is the one that did.

    Idempotent: revoking twice is normal - a client retrying a refresh on a
    dropped connection does exactly that - and must not raise.

    A read-then-write would not be enough. Within one session the pending
    INSERT is invisible to a SELECT until it flushes, and across sessions two
    concurrent refreshes presenting the same token would both see it absent
    and both insert. ON CONFLICT DO NOTHING settles both cases in the database,
    where the uniqueness actually lives.
    """
    result = await session.execute(
        insert(RevokedRefreshToken)
        .values(
            jti=jti,
            user_id=user_id,
            reason=reason,
            expires_at=expires_at,
        )
        .on_conflict_do_nothing(index_elements=["jti"])
    )
    # False means another request got there first. Two refreshes racing on one
    # token both pass the is_revoked check, and only this row count tells them
    # apart: without it a replay issued a second live token family unnoticed.
    return bool(result.rowcount)


async def revoke_all_for_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    reason: str,
) -> None:
    """End every session for a user by rotating their signing horizon forward.

    Individual outstanding tokens cannot be enumerated - they are bearer
    credentials the server never stored - so the user's `sessions_valid_from`
    is moved to now, and any token issued before that instant is refused.
    """
    user = await session.get(User, user_id)
    if user is None:
        return
    user.sessions_valid_from = datetime.now(timezone.utc)
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=user.sessions_valid_from)
    )
    session.add(
        AuditLog(
            user_id=user_id,
            action="auth.sessions_revoked",
            resource_type="user",
            resource_id=user_id,
            metadata_={"reason": reason},
        )
    )


async def purge_expired(session: AsyncSession) -> int:
    """Drop revocations for tokens that have expired on their own.

    Without this the table grows for the life of the deployment, holding rows
    that can no longer affect a decision.
    """
    result = await session.execute(
        delete(RevokedRefreshToken).where(
            RevokedRefreshToken.expires_at < datetime.now(timezone.utc)
        )
    )
    return int(result.rowcount or 0)
