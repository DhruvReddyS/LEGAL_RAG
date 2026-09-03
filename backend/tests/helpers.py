from __future__ import annotations

import uuid

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models import User
from app.models.enums import UserRole


async def provision_test_user(*, name: str, email: str, password: str, role: str) -> dict:
    async with AsyncSessionLocal() as session:
        user = User(
            name=name,
            email=email,
            hashed_password=hash_password(password),
            role=UserRole(role),
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return {
            "access_token": create_access_token(user),
            "refresh_token": create_refresh_token(user),
            "user": {
                "id": str(user.id),
                "email": user.email,
                "role": user.role.value,
            },
        }


def unique_email(prefix: str) -> str:
    """A fresh address per run.

    The integration database persists between runs, so a fixed address fails
    the unique index the second time. `.test` is deliberately avoided: it is a
    reserved TLD that email-validator rejects, so an address using it can be
    inserted directly but never passed through /auth/login, which validates.
    """
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"
