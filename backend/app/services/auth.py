from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import User
from app.schemas.auth import RegisterRequest


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email.strip().lower()))


async def create_user(session: AsyncSession, registration: RegisterRequest) -> User:
    user = User(
        name=registration.name,
        email=str(registration.email),
        hashed_password=hash_password(registration.password),
        role=registration.role,
    )
    session.add(user)
    await session.flush()
    return user


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> User | None:
    user = await get_user_by_email(session, email)
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        return None
    return user
