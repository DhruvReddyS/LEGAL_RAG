"""The two things that stop a signed-in account using the product.

Checked by the permission dependency, so it covers every product route at once.
Account routes authenticate without it, because they are how a person clears
either condition: accepting the notice, changing the password, or leaving.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import ConsentRecord, User, UserSecurity
from app.services.privacy_notice import PRIVACY_NOTICE_VERSION

CONSENT_REQUIRED = "consent_required"
PASSWORD_CHANGE_REQUIRED = "password_change_required"


async def assert_account_may_proceed(session: AsyncSession, user: User) -> None:
    must_change = await session.scalar(
        select(UserSecurity.must_change_password).where(UserSecurity.user_id == user.id)
    )
    if must_change:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PASSWORD_CHANGE_REQUIRED,
        )
    if not settings.consent_is_enforced:
        return
    accepted = await session.scalar(
        select(ConsentRecord.id)
        .where(
            ConsentRecord.user_id == user.id,
            ConsentRecord.notice_version == PRIVACY_NOTICE_VERSION,
            ConsentRecord.withdrawn_at.is_(None),
        )
        .limit(1)
    )
    if accepted is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=CONSENT_REQUIRED)
