from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.models import User
from app.schemas.auth import TokenPayload


password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_context.verify(plain_password, hashed_password)


def _create_token(
    user: User,
    *,
    token_type: str,
    secret: str,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "exp": now + expires_delta,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": token_type,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def create_access_token(user: User) -> str:
    return _create_token(
        user,
        token_type="access",
        secret=settings.jwt_secret_key.get_secret_value(),
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user: User) -> str:
    return _create_token(
        user,
        token_type="refresh",
        secret=settings.jwt_refresh_secret_key.get_secret_value(),
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, *, expected_type: str) -> TokenPayload:
    secret = (
        settings.jwt_secret_key.get_secret_value()
        if expected_type == "access"
        else settings.jwt_refresh_secret_key.get_secret_value()
    )
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
        token_payload = TokenPayload.model_validate(payload)
    except (JWTError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if token_payload.type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_payload


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    user = await get_optional_current_user(credentials, session, request=request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None,
    session: AsyncSession,
    *,
    request: Request | None = None,
) -> User | None:
    if credentials is None and request is not None:
        cookie_token = request.cookies.get("legal_rag_access")
        if cookie_token:
            credentials = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=cookie_token
            )
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None

    payload = decode_token(credentials.credentials, expected_type="access")
    user = await session.get(User, payload.sub)
    if user is None or not user.is_active or user.role != payload.role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive, no longer exists, or role has changed",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
