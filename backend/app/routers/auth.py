from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from app.models import AuditLog, User
from app.models.enums import UserRole
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
)
from app.services.auth import authenticate_user, create_user, get_user_by_email


router = APIRouter(prefix="/auth", tags=["authentication"])


def _set_auth_cookies(response: Response, tokens: TokenPairResponse) -> None:
    secure = settings.auth_cookie_secure
    response.set_cookie(
        "legal_rag_access",
        tokens.access_token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    response.set_cookie(
        "legal_rag_refresh",
        tokens.refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        httponly=True,
        secure=secure,
        samesite=settings.cookie_samesite,
        path="/auth/cookie",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("legal_rag_access", path="/")
    response.delete_cookie("legal_rag_refresh", path="/auth/cookie")


def build_token_pair(user: User) -> TokenPairResponse:
    return TokenPairResponse(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(user),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/register",
    response_model=TokenPairResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    registration: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenPairResponse:
    if registration.role is not UserRole.CITIZEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Police and advocate accounts must be provisioned by an administrator",
        )
    if await get_user_by_email(session, str(registration.email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    try:
        user = await create_user(session, registration)
        session.add(
            AuditLog(
                user_id=user.id,
                action="auth.register",
                resource_type="user",
                resource_id=user.id,
                metadata_={"role": user.role.value},
            )
        )
        await session.commit()
        await session.refresh(user)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc

    return build_token_pair(user)


@router.post("/login", response_model=TokenPairResponse)
async def login(
    credentials: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenPairResponse:
    user = await authenticate_user(
        session,
        str(credentials.email),
        credentials.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session.add(
        AuditLog(
            user_id=user.id,
            action="auth.login",
            resource_type="user",
            resource_id=user.id,
            metadata_={},
        )
    )
    await session.commit()
    return build_token_pair(user)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_tokens(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenPairResponse:
    payload = decode_token(request.refresh_token, expected_type="refresh")
    user = await session.get(User, payload.sub)
    if user is None or not user.is_active or user.role != payload.role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive, no longer exists, or role has changed",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session.add(
        AuditLog(
            user_id=user.id,
            action="auth.refresh",
            resource_type="user",
            resource_id=user.id,
            metadata_={"rotated_jti": str(payload.jti)},
        )
    )
    await session.commit()
    return build_token_pair(user)


@router.get("/me", response_model=UserResponse)
async def read_current_user(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post("/cookie/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def cookie_register(
    registration: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    tokens = await register(registration, session)
    _set_auth_cookies(response, tokens)
    return tokens.user


@router.post("/cookie/login", response_model=UserResponse)
async def cookie_login(
    credentials: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    tokens = await login(credentials, session)
    _set_auth_cookies(response, tokens)
    return tokens.user


@router.post("/cookie/refresh", response_model=UserResponse)
async def cookie_refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    refresh_cookie = request.cookies.get("legal_rag_refresh")
    if not refresh_cookie:
        raise HTTPException(status_code=401, detail="Refresh cookie required")
    tokens = await refresh_tokens(RefreshRequest(refresh_token=refresh_cookie), session)
    _set_auth_cookies(response, tokens)
    return tokens.user


@router.post("/cookie/logout", status_code=status.HTTP_204_NO_CONTENT)
async def cookie_logout(response: Response) -> None:
    _clear_auth_cookies(response)
