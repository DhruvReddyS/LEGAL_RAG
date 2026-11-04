"""Account recovery, device sessions and the rights a person has over their data.

These routes authenticate with get_current_user rather than a permission, on
purpose: someone who has not accepted the notice, or must change their password,
has to be able to reach them. That is how those conditions get cleared.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.permissions import ADMIN_USER_MANAGE
from app.core.rbac import require_permission
from app.core.security import (
    bearer_scheme,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    verify_password,
)
from app.models import AccountFlag, AuditLog, User, UserSecurity
from app.schemas.account import (
    AccountStatus,
    AdminErasureRequest,
    AdminResetCodeRequest,
    AdminResetCodeResponse,
    ConsentAccept,
    ConsentState,
    DeviceSession,
    DeviceSessionList,
    ErasureRequest,
    ErasureResponse,
    MfaCode,
    MfaEnrollResponse,
    PasswordChange,
    PrivacyConfiguration,
    ProfileUpdate,
    RecoveryCodes,
    ResetCodeRedeem,
    ResetCodeRequest,
    RetentionRun,
    RetentionStatus,
    StepUp,
)
from app.schemas.auth import UserResponse
from app.services import account_security, privacy
from app.services.auth import get_user_by_email
from app.services.rate_limit import RateLimitExceeded, user_rate_limiter


router = APIRouter(prefix="/account", tags=["account"])

ERASE_SELF_PHRASE = "ERASE MY ACCOUNT"
ERASE_OTHER_PHRASE = "ERASE THIS ACCOUNT"


def _current_session_id(request: Request, credentials) -> uuid.UUID | None:
    token = credentials.credentials if credentials else request.cookies.get("legal_rag_access")
    if not token:
        return None
    return decode_token(token, expected_type="access").sid


async def _admit_public(request: Request, email: str, bucket: str) -> None:
    client_host = request.client.host if request.client else "unknown"
    for identity, name in ((email.casefold(), f"{bucket}_account"), (client_host, f"{bucket}_source")):
        try:
            await user_rate_limiter.admit(
                identity, name, limit=settings.login_attempts_per_account_per_minute
            )
        except RateLimitExceeded as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Try again shortly.",
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc


def _erasure_failed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Your data could not be fully erased just now, so your account was kept. Please try again shortly.",
        headers={"Retry-After": "60"},
    )


# ---------------------------------------------------------------- public routes


@router.get("/privacy", response_model=PrivacyConfiguration)
async def read_privacy_configuration() -> dict:
    """Public: the notice has to be readable before an account exists."""
    return privacy.privacy_configuration()


@router.post("/password-reset/redeem", status_code=status.HTTP_204_NO_CONTENT)
async def redeem_password_reset(
    payload: ResetCodeRedeem,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    email = str(payload.email).strip().lower()
    await _admit_public(request, email, "reset_redeem")
    user = await get_user_by_email(session, email)
    await account_security.redeem_reset_code(session, user, payload.code, payload.new_password)
    await session.commit()


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    payload: ResetCodeRequest,
    request: Request,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """The same answer whether or not the address exists, or mail is configured."""
    email = str(payload.email).strip().lower()
    await _admit_public(request, email, "reset_request")
    if settings.self_service_reset_available:
        user = await get_user_by_email(session, email)
        if user is not None and user.is_active:
            code, _ = await account_security.issue_reset_code(session, user, issued_by=None)
            session.add(
                AuditLog(
                    user_id=user.id,
                    action="account.password_reset_mailed",
                    resource_type="user",
                    resource_id=user.id,
                    metadata_={},
                )
            )
            await session.commit()
            background.add_task(account_security.send_reset_mail, user.email, code)
    return {"status": "accepted"}


# ----------------------------------------------------------------- your account


@router.get("/status", response_model=AccountStatus)
async def account_status(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AccountStatus:
    row = await session.get(UserSecurity, user.id)
    enabled = bool(row and row.totp_confirmed_at and row.totp_secret_encrypted)
    flags = await session.get(AccountFlag, user.id)
    return AccountStatus(
        mfa_enabled=enabled,
        mfa_pending=bool(row and row.totp_secret_encrypted and not row.totp_confirmed_at),
        recovery_codes_remaining=await account_security.remaining_recovery_codes(session, user.id),
        must_change_password=bool(row and row.must_change_password)
        or bool(flags and flags.force_password_reset),
        mfa_setup_required=bool(flags and flags.mfa_required and not enabled),
        password_changed_at=row.password_changed_at if row else None,
        consent=ConsentState(**await privacy.consent_state(session, user)),
    )


@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Correcting what is held about you. The address needs the password."""
    if payload.email is not None:
        await account_security.admit_step_up(user)
        if not payload.current_password or not verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password is not correct")
        user.email = str(payload.email).strip().lower()
    if payload.name is not None:
        user.name = payload.name
    session.add(
        AuditLog(
            user_id=user.id,
            action="account.profile_updated",
            resource_type="user",
            resource_id=user.id,
            metadata_={"name": payload.name is not None, "email": payload.email is not None},
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That address is already in use") from exc
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/password")
async def change_password(
    payload: PasswordChange,
    request: Request,
    response: Response,
    credentials=Depends(bearer_scheme),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Change the password and end every other device.

    This session continues under new tokens, set the way it presented its old
    one: a browser gets new cookies and never sees a token in JavaScript, and a
    bearer client gets them in the body, since it already holds tokens there.
    """
    await account_security.admit_step_up(user)
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password is not correct")
    sid = _current_session_id(request, credentials)
    await account_security.set_password(session, user, payload.new_password, keep_session=sid)
    session.add(
        AuditLog(
            user_id=user.id,
            action="account.password_changed",
            resource_type="user",
            resource_id=user.id,
            metadata_={},
        )
    )
    await session.commit()
    access, refresh = create_access_token(user, sid), create_refresh_token(user, sid)
    if credentials is None:
        from app.routers.auth import set_auth_cookie_pair

        set_auth_cookie_pair(response, access, refresh)
        return {"status": "changed"}
    return {"status": "changed", "access_token": access, "refresh_token": refresh}


# ------------------------------------------------------------------- the notice


@router.get("/consent", response_model=ConsentState)
async def read_consent(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ConsentState:
    return ConsentState(**await privacy.consent_state(session, user))


@router.post("/consent", response_model=ConsentState)
async def accept_consent(
    payload: ConsentAccept,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ConsentState:
    await privacy.record_consent(session, user.id, payload.notice_version, source="notice")
    await session.commit()
    return ConsentState(**await privacy.consent_state(session, user))


@router.post("/consent/withdraw", response_model=ConsentState)
async def withdraw_consent(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ConsentState:
    await privacy.withdraw_consent(session, user)
    await session.commit()
    return ConsentState(**await privacy.consent_state(session, user))


# -------------------------------------------------------------- signed-in devices


@router.get("/sessions", response_model=DeviceSessionList)
async def list_device_sessions(
    request: Request,
    credentials=Depends(bearer_scheme),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DeviceSessionList:
    current = _current_session_id(request, credentials)
    return DeviceSessionList(
        items=[
            DeviceSession(
                id=row.id,
                label=row.label,
                created_at=row.created_at,
                last_seen_at=row.last_seen_at,
                current=row.id == current,
            )
            for row in await account_security.active_sessions(session, user)
        ]
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    await account_security.revoke_session(session, user, session_id)
    await session.commit()


@router.post("/sessions/revoke-others")
async def revoke_other_device_sessions(
    request: Request,
    credentials=Depends(bearer_scheme),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    keep = _current_session_id(request, credentials)
    revoked = await account_security.revoke_other_sessions(session, user, keep)
    session.add(
        AuditLog(
            user_id=user.id,
            action="account.other_sessions_revoked",
            resource_type="user",
            resource_id=user.id,
            metadata_={"revoked": revoked},
        )
    )
    await session.commit()
    return {"revoked": revoked}


# ---------------------------------------------------------------- second factor


@router.post("/mfa/enroll", response_model=MfaEnrollResponse)
async def enroll_mfa(
    payload: StepUp,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MfaEnrollResponse:
    # Before the step-up, which would otherwise ask an enrolled account for the
    # very factor this route exists to set up.
    if await account_security.mfa_is_enabled(session, user.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-step sign-in is already on")
    await account_security.verify_step_up(session, user, payload.password)
    secret, uri = await account_security.begin_mfa_enrollment(session, user)
    await session.commit()
    return MfaEnrollResponse(secret=secret, otpauth_uri=uri)


@router.post("/mfa/confirm", response_model=RecoveryCodes)
async def confirm_mfa(
    payload: MfaCode,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RecoveryCodes:
    codes = await account_security.confirm_mfa_enrollment(session, user, payload.code)
    await session.commit()
    return RecoveryCodes(codes=codes)


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_mfa(
    payload: StepUp,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    if not await account_security.mfa_is_enabled(session, user.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-step sign-in is off")
    await account_security.verify_step_up(
        session, user, payload.password, payload.mfa_code, payload.recovery_code
    )
    await account_security.clear_mfa(session, user.id)
    session.add(
        AuditLog(
            user_id=user.id,
            action="account.mfa_disabled",
            resource_type="user",
            resource_id=user.id,
            metadata_={},
        )
    )
    await session.commit()


@router.post("/mfa/recovery-codes", response_model=RecoveryCodes)
async def new_recovery_codes(
    payload: StepUp,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> RecoveryCodes:
    await account_security.verify_step_up(
        session, user, payload.password, payload.mfa_code, payload.recovery_code
    )
    codes = await account_security.regenerate_recovery_codes(session, user)
    session.add(
        AuditLog(
            user_id=user.id,
            action="account.recovery_codes_replaced",
            resource_type="user",
            resource_id=user.id,
            metadata_={},
        )
    )
    await session.commit()
    return RecoveryCodes(codes=codes)


# ------------------------------------------------------------------- your rights


@router.post("/export")
async def export_my_data(
    payload: StepUp,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Everything held about you, as one JSON file.

    A step-up and a POST: this is the whole record in one response, so a borrowed
    session should not be enough, and it must not be fetchable from a link.
    """
    await account_security.verify_step_up(
        session, user, payload.password, payload.mfa_code, payload.recovery_code
    )
    export = await privacy.build_export(session, user)
    session.add(
        AuditLog(
            user_id=user.id,
            action="privacy.data_exported",
            resource_type="user",
            resource_id=user.id,
            metadata_={"conversations": len(export["conversations"]), "cases": len(export["cases"])},
        )
    )
    await session.commit()
    return Response(
        content=json.dumps(export, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="corpusil-my-data.json"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/erase", response_model=ErasureResponse)
async def erase_my_account(
    payload: ErasureRequest,
    response: Response,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ErasureResponse:
    if payload.confirm != ERASE_SELF_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f'Type "{ERASE_SELF_PHRASE}" to confirm',
        )
    await account_security.verify_step_up(
        session, user, payload.password, payload.mfa_code, payload.recovery_code
    )
    # Commit the consumed second factor before the long part, so a failed
    # erasure that is retried cannot replay the same one-time code.
    await session.commit()
    try:
        result = await privacy.erase_account(session, user, initiated_by="self")
    except privacy.ErasureIncomplete as exc:
        raise _erasure_failed() from exc
    response.delete_cookie("legal_rag_access", path="/")
    response.delete_cookie("legal_rag_refresh", path="/auth/cookie")
    return ErasureResponse(receipt_id=result.receipt_id, counts=result.counts)


# --------------------------------------------------------------- administrators


@router.post("/admin/reset-code", response_model=AdminResetCodeResponse)
async def admin_issue_reset_code(
    payload: AdminResetCodeRequest,
    admin: Annotated[User, Depends(require_permission(ADMIN_USER_MANAGE))],
    session: AsyncSession = Depends(get_db_session),
) -> AdminResetCodeResponse:
    """Issue a one-time code to hand over in person or on a trusted channel.

    The way back into an account when no mail relay exists. The administrator
    sees the code once and never learns the password that replaces it.
    """
    target = await get_user_by_email(session, str(payload.email))
    if target is None:
        raise HTTPException(status_code=404, detail="No account with that address")
    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Change your own password from your account settings",
        )
    code, expires_at = await account_security.issue_reset_code(session, target, issued_by=admin.id)
    if payload.reset_mfa:
        await account_security.clear_mfa(session, target.id)
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.reset_code_issued",
            resource_type="user",
            resource_id=target.id,
            metadata_={"mfa_cleared": payload.reset_mfa},
        )
    )
    await session.commit()
    return AdminResetCodeResponse(code=code, expires_at=expires_at, mfa_cleared=payload.reset_mfa)


@router.post("/admin/erase", response_model=ErasureResponse)
async def admin_erase_account(
    payload: AdminErasureRequest,
    admin: Annotated[User, Depends(require_permission(ADMIN_USER_MANAGE))],
    session: AsyncSession = Depends(get_db_session),
) -> ErasureResponse:
    """Carry out an erasure request from someone who cannot sign in.

    Erases without reading: nothing about the account's contents is returned, so
    this does not become a way to reach private case material.
    """
    if payload.confirm != ERASE_OTHER_PHRASE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f'Type "{ERASE_OTHER_PHRASE}" to confirm',
        )
    await account_security.verify_step_up(session, admin, payload.admin_password, payload.mfa_code)
    target = await get_user_by_email(session, str(payload.email))
    if target is None:
        raise HTTPException(status_code=404, detail="No account with that address")
    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Erase your own account from your account settings",
        )
    await session.commit()
    try:
        result = await privacy.erase_account(session, target, initiated_by="admin")
    except privacy.ErasureIncomplete as exc:
        raise _erasure_failed() from exc
    return ErasureResponse(receipt_id=result.receipt_id, counts=result.counts)


@router.get("/admin/retention", response_model=RetentionStatus)
async def admin_retention_status(
    _: Annotated[User, Depends(require_permission(ADMIN_USER_MANAGE))],
    session: AsyncSession = Depends(get_db_session),
) -> RetentionStatus:
    policy = privacy.retention_policy()
    due = await privacy.expired_conversation_ids(session, days=policy["chat_retention_days"])
    return RetentionStatus(**policy, conversations_past_retention=len(due))


@router.post("/admin/retention/run", response_model=RetentionRun)
async def admin_run_retention(
    _: Annotated[User, Depends(require_permission(ADMIN_USER_MANAGE))],
    session: AsyncSession = Depends(get_db_session),
) -> RetentionRun:
    erased = await privacy.apply_retention(session)
    await session.commit()
    return RetentionRun(erased_conversations=erased)
