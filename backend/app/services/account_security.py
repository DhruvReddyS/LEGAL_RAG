"""Passwords, second factor, one-time reset codes and device sessions.

Every secret here is either hashed or encrypted before it is stored, and none
of them may reach a log, an audit row or an error message. Audit metadata in
this module carries counts and ids only.
"""

from __future__ import annotations

import logging
import re
import secrets
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models import (
    AccountFlag,
    AuditLog,
    PasswordResetCode,
    RecoveryCode,
    User,
    UserSecurity,
    UserSession,
)
from app.services import totp
from app.services.rate_limit import RateLimitExceeded, user_rate_limiter

logger = logging.getLogger("legal_rag.account")

MFA_REQUIRED = "mfa_required"
MFA_INVALID = "mfa_invalid"
RECOVERY_CODE_COUNT = 10
# Step-up checks run on an already signed-in session, so a stolen cookie must
# not get unlimited guesses at the password or the code behind it.
STEP_UP_ATTEMPTS_PER_MINUTE = 5


def describe_device(user_agent: str | None, *, origin: str | None = None) -> str:
    """A label a person can recognise, derived and then thrown away.

    Only the label is stored. The raw user-agent string is a fingerprint nobody
    needs in order to tell their laptop from their phone.
    """
    agent = user_agent or ""
    if re.search(r"iPhone|iPad", agent):
        system = "iOS"
    elif "Android" in agent:
        system = "Android"
    elif "Windows" in agent:
        system = "Windows"
    elif "Mac OS X" in agent or "Macintosh" in agent:
        system = "macOS"
    elif "Linux" in agent or "X11" in agent:
        system = "Linux"
    else:
        system = ""
    if origin and ("tauri" in origin):
        browser = "Corpusil desktop"
    elif "Edg/" in agent:
        browser = "Edge"
    elif "Firefox/" in agent:
        browser = "Firefox"
    elif "Chrome/" in agent or "CriOS/" in agent:
        browser = "Chrome"
    elif "Safari/" in agent:
        browser = "Safari"
    else:
        browser = ""
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or "Unknown device"


def device_label(request: Request | None) -> str:
    if request is None:
        return "Unknown device"
    return describe_device(request.headers.get("user-agent"), origin=request.headers.get("origin"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def open_session(session: AsyncSession, user: User, label: str) -> uuid.UUID:
    device = UserSession(
        user_id=user.id,
        label=label,
        expires_at=_utcnow() + timedelta(days=settings.refresh_token_expire_days),
    )
    session.add(device)
    await session.flush()
    return device.id


async def active_sessions(session: AsyncSession, user: User) -> list[UserSession]:
    rows = await session.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > _utcnow(),
        )
        .order_by(UserSession.last_seen_at.desc())
    )
    return list(rows.all())


async def revoke_session(session: AsyncSession, user: User, session_id: uuid.UUID) -> None:
    """Scoped to the owner in the statement, so another user's id is just absent."""
    result = await session.execute(
        update(UserSession)
        .where(
            UserSession.id == session_id,
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=_utcnow())
    )
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Session not found")
    session.add(
        AuditLog(
            user_id=user.id,
            action="account.session_revoked",
            resource_type="user_session",
            resource_id=session_id,
            metadata_={},
        )
    )


async def revoke_other_sessions(
    session: AsyncSession, user: User, keep: uuid.UUID | None
) -> int:
    statement = update(UserSession).where(
        UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
    )
    if keep is not None:
        statement = statement.where(UserSession.id != keep)
    result = await session.execute(statement.values(revoked_at=_utcnow()))
    return int(result.rowcount or 0)


async def _security_row(session: AsyncSession, user_id: uuid.UUID) -> UserSecurity:
    row = await session.get(UserSecurity, user_id)
    if row is None:
        row = UserSecurity(user_id=user_id)
        session.add(row)
        await session.flush()
    return row


async def admit_step_up(user: User) -> None:
    try:
        await user_rate_limiter.admit(
            str(user.id), "account_step_up", limit=STEP_UP_ATTEMPTS_PER_MINUTE
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again shortly.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc


async def mfa_is_enabled(session: AsyncSession, user_id: uuid.UUID) -> bool:
    row = await session.get(UserSecurity, user_id)
    return bool(row and row.totp_confirmed_at and row.totp_secret_encrypted)


async def _accept_totp(session: AsyncSession, row: UserSecurity, code: str) -> bool:
    secret = totp.decrypt_secret(row.totp_secret_encrypted or "")
    if secret is None:
        return False
    step = totp.matching_step(secret, code)
    if step is None:
        return False
    # Conditional in the database: two requests holding the same code cannot
    # both succeed, however closely they race.
    result = await session.execute(
        update(UserSecurity)
        .where(UserSecurity.user_id == row.user_id, UserSecurity.totp_last_step < step)
        .values(totp_last_step=step)
    )
    if not result.rowcount:
        return False
    row.totp_last_step = step
    return True


async def _accept_recovery_code(session: AsyncSession, user_id: uuid.UUID, code: str) -> bool:
    result = await session.execute(
        update(RecoveryCode)
        .where(
            RecoveryCode.user_id == user_id,
            RecoveryCode.code_hash == totp.hash_one_time_value(code),
            RecoveryCode.used_at.is_(None),
        )
        .values(used_at=_utcnow())
    )
    if not result.rowcount:
        return False
    session.add(
        AuditLog(
            user_id=user_id,
            action="account.recovery_code_used",
            resource_type="user",
            resource_id=user_id,
            metadata_={},
        )
    )
    return True


async def check_second_factor(
    session: AsyncSession,
    user: User,
    mfa_code: str | None,
    recovery_code: str | None,
) -> None:
    """Raise unless a required second factor was supplied and is right."""
    row = await session.get(UserSecurity, user.id)
    if not (row and row.totp_confirmed_at and row.totp_secret_encrypted):
        return
    if not mfa_code and not recovery_code:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MFA_REQUIRED)
    if mfa_code and await _accept_totp(session, row, mfa_code):
        return
    if recovery_code and await _accept_recovery_code(session, user.id, recovery_code):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MFA_INVALID)


async def verify_step_up(
    session: AsyncSession,
    user: User,
    password: str,
    mfa_code: str | None = None,
    recovery_code: str | None = None,
) -> None:
    """Prove it is really the account holder before something irreversible."""
    await admit_step_up(user)
    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Password is not correct")
    try:
        await check_second_factor(session, user, mfa_code, recovery_code)
    except HTTPException as exc:
        # 401 from here would send the client to refresh its session.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.detail) from exc


async def set_password(
    session: AsyncSession,
    user: User,
    new_password: str,
    *,
    keep_session: uuid.UUID | None,
) -> None:
    """Replace the password and end every session except the one making the change."""
    if verify_password(new_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Choose a password different from the current one",
        )
    user.hashed_password = hash_password(new_password)
    row = await _security_row(session, user.id)
    row.must_change_password = False
    row.password_changed_at = _utcnow()
    flags = await session.get(AccountFlag, user.id)
    if flags is not None:
        flags.force_password_reset = False
    await revoke_other_sessions(session, user, keep_session)
    # Tokens carrying no session id cannot be revoked one by one. Whole seconds,
    # because JWT `iat` is whole seconds: microseconds here would reject the
    # token issued immediately after this change.
    user.sessions_valid_from = _utcnow().replace(microsecond=0)


# --------------------------------------------------------------- second factor


async def begin_mfa_enrollment(session: AsyncSession, user: User) -> tuple[str, str]:
    row = await _security_row(session, user.id)
    if row.totp_confirmed_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-step sign-in is already on")
    secret = totp.generate_secret()
    row.totp_secret_encrypted = totp.encrypt_secret(secret)
    row.totp_last_step = 0
    return secret, totp.provisioning_uri(secret, user.email, settings.mfa_issuer)


async def _replace_recovery_codes(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    from sqlalchemy import delete

    await session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))
    codes = [totp.generate_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    session.add_all(
        RecoveryCode(user_id=user_id, code_hash=totp.hash_one_time_value(code)) for code in codes
    )
    return codes


async def confirm_mfa_enrollment(session: AsyncSession, user: User, code: str) -> list[str]:
    row = await session.get(UserSecurity, user.id)
    if row is None or not row.totp_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Start enrolment first")
    if row.totp_confirmed_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-step sign-in is already on")
    await admit_step_up(user)
    if not await _accept_totp(session, row, code):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That code is not correct")
    row.totp_confirmed_at = _utcnow()
    codes = await _replace_recovery_codes(session, user.id)
    session.add(
        AuditLog(
            user_id=user.id,
            action="account.mfa_enabled",
            resource_type="user",
            resource_id=user.id,
            metadata_={},
        )
    )
    return codes


async def regenerate_recovery_codes(session: AsyncSession, user: User) -> list[str]:
    if not await mfa_is_enabled(session, user.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-step sign-in is off")
    return await _replace_recovery_codes(session, user.id)


async def clear_mfa(session: AsyncSession, user_id: uuid.UUID) -> None:
    from sqlalchemy import delete

    row = await session.get(UserSecurity, user_id)
    if row is not None:
        row.totp_secret_encrypted = None
        row.totp_confirmed_at = None
        row.totp_last_step = 0
    await session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id))


async def remaining_recovery_codes(session: AsyncSession, user_id: uuid.UUID) -> int:
    from sqlalchemy import func

    return int(
        await session.scalar(
            select(func.count())
            .select_from(RecoveryCode)
            .where(RecoveryCode.user_id == user_id, RecoveryCode.used_at.is_(None))
        )
        or 0
    )


# --------------------------------------------------------- one-time reset codes


async def issue_reset_code(
    session: AsyncSession, target: User, *, issued_by: uuid.UUID | None
) -> tuple[str, datetime]:
    """Create a code, replacing any still outstanding. Returned once, never stored."""
    now = _utcnow()
    await session.execute(
        update(PasswordResetCode)
        .where(PasswordResetCode.user_id == target.id, PasswordResetCode.used_at.is_(None))
        .values(used_at=now)
    )
    code = secrets.token_urlsafe(24)
    expires_at = now + timedelta(minutes=settings.password_reset_ttl_minutes)
    session.add(
        PasswordResetCode(
            user_id=target.id,
            code_hash=totp.hash_one_time_value(code),
            issued_by=issued_by,
            expires_at=expires_at,
        )
    )
    return code, expires_at


async def redeem_reset_code(
    session: AsyncSession, user: User | None, code: str, new_password: str
) -> None:
    """One refusal for every failure: a stranger learns nothing from the wording."""
    refusal = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This reset code is not valid")
    if user is None or not user.is_active:
        raise refusal
    now = _utcnow()
    # The hash is matched against this user's codes only, so a code issued for
    # one account does nothing when presented with another's address.
    result = await session.execute(
        update(PasswordResetCode)
        .where(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.code_hash == totp.hash_one_time_value(code),
            PasswordResetCode.used_at.is_(None),
            PasswordResetCode.expires_at > now,
        )
        .values(used_at=now)
    )
    if not result.rowcount:
        raise refusal
    await set_password(session, user, new_password, keep_session=None)
    session.add(
        AuditLog(
            user_id=user.id,
            action="account.password_reset_redeemed",
            resource_type="user",
            resource_id=user.id,
            metadata_={},
        )
    )


def send_reset_mail(to_address: str, code: str) -> None:
    """Best effort, off the request path. Only used when SMTP is configured."""
    message = EmailMessage()
    message["Subject"] = "Your Corpusil password reset code"
    message["From"] = settings.smtp_from
    message["To"] = to_address
    message.set_content(
        "Someone asked to reset the password on your Corpusil account.\n\n"
        f"Your one-time code is:\n\n{code}\n\n"
        f"It works once and expires in {settings.password_reset_ttl_minutes} minutes. "
        "Enter it on the sign-in screen under “Forgot your password?”.\n\n"
        "If this was not you, you can ignore this message: your password has not changed.\n"
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as client:
            if settings.smtp_use_tls:
                client.starttls()
            if settings.smtp_username and settings.smtp_password is not None:
                client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            client.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        # The type only. The address and the code stay out of the log.
        logger.warning("password reset mail not delivered: %s", type(exc).__name__)
