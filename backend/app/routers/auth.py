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
from app.services.rate_limit import RateLimitExceeded, user_rate_limiter
from app.services import token_revocation
from app.core.config import settings


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


async def _admit_login_attempt(request: Request, email: str) -> None:
    """Throttle by account and by source before any password verification.

    Two buckets, because either alone is bypassable: per-account stops a
    password list against one victim, per-source stops one client spraying many
    accounts. Both are checked before bcrypt runs, so a refused attempt costs
    no work.
    """
    client_host = request.client.host if request.client else "unknown"
    for identity, bucket, limit in (
        (email.casefold(), "login_account", settings.login_attempts_per_account_per_minute),
        (client_host, "login_source", settings.login_attempts_per_minute),
    ):
        try:
            await user_rate_limiter.admit(identity, bucket, limit=limit)
        except RateLimitExceeded as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                # Deliberately identical wording for both buckets: saying which
                # one tripped tells an attacker whether the account exists.
                detail="Too many sign-in attempts. Try again shortly.",
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc


@router.post("/login", response_model=TokenPairResponse)
async def login(
    credentials: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenPairResponse:
    await _admit_login_attempt(request, str(credentials.email))
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

    # Presenting a token that was already consumed is not a retry: rotation
    # replaced it, so either it was stolen or the holder's copy was. Treat it
    # as compromise and end every session rather than refusing this one call
    # and leaving the thief's newer token working.
    if await token_revocation.is_revoked(session, payload.jti):
        await token_revocation.revoke_all_for_user(
            session,
            user_id=user.id,
            reason=token_revocation.REASON_REUSE_DETECTED,
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session ended. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.sessions_valid_from is not None and payload.iat < user.sessions_valid_from:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session ended. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await token_revocation.revoke(
        session,
        jti=payload.jti,
        user_id=user.id,
        expires_at=payload.exp,
        reason=token_revocation.REASON_ROTATED,
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
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    tokens = await login(credentials, request, session)
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
async def cookie_logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """End the session server-side, then clear the cookies.

    Clearing a cookie is an instruction to one browser. Without revocation a
    token copied off a shared machine kept working for its remaining lifetime,
    and signing out did nothing an attacker had to care about.
    """
    refresh_cookie = request.cookies.get("legal_rag_refresh")
    if refresh_cookie:
        try:
            payload = decode_token(refresh_cookie, expected_type="refresh")
        except HTTPException:
            # An expired or malformed cookie needs no revocation, and logout
            # must succeed regardless so the browser state is always cleared.
            payload = None
        if payload is not None:
            await token_revocation.revoke(
                session,
                jti=payload.jti,
                user_id=payload.sub,
                expires_at=payload.exp,
                reason=token_revocation.REASON_LOGOUT,
            )
            session.add(
                AuditLog(
                    user_id=payload.sub,
                    action="auth.logout",
                    resource_type="user",
                    resource_id=payload.sub,
                    metadata_={"revoked_jti": str(payload.jti)},
                )
            )
            await session.commit()
    _clear_auth_cookies(response)
