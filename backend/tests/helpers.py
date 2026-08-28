from __future__ import annotations

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
