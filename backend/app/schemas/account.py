from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


def _bcrypt_safe(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("password must not exceed 72 UTF-8 bytes")
    return value


class StepUp(BaseModel):
    """Re-proving who you are before something that cannot be taken back."""

    password: str = Field(min_length=1, max_length=72)
    mfa_code: str | None = Field(default=None, max_length=16)
    recovery_code: str | None = Field(default=None, max_length=32)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=12, max_length=72)

    _limit = field_validator("new_password")(_bcrypt_safe)


class ResetCodeRedeem(BaseModel):
    email: EmailStr
    code: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=12, max_length=72)

    _limit = field_validator("new_password")(_bcrypt_safe)


class ResetCodeRequest(BaseModel):
    email: EmailStr


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    # Required to change the address, which is the sign-in identity.
    current_password: str | None = Field(default=None, max_length=72)

    @field_validator("name")
    @classmethod
    def tidy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if len(cleaned) < 2:
            raise ValueError("name must contain at least two visible characters")
        return cleaned


class MfaEnrollResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=16)


class RecoveryCodes(BaseModel):
    codes: list[str]


class ConsentAccept(BaseModel):
    notice_version: str = Field(min_length=1, max_length=32)


class ConsentState(BaseModel):
    current_version: str
    accepted_version: str | None
    accepted_at: datetime | None
    withdrawn_at: datetime | None
    required: bool


class AccountStatus(BaseModel):
    mfa_enabled: bool
    mfa_pending: bool
    recovery_codes_remaining: int
    must_change_password: bool
    mfa_setup_required: bool = False
    password_changed_at: datetime | None
    consent: ConsentState


class DeviceSession(BaseModel):
    id: uuid.UUID
    label: str
    created_at: datetime
    last_seen_at: datetime
    current: bool


class DeviceSessionList(BaseModel):
    items: list[DeviceSession]


class ErasureRequest(StepUp):
    # Typed out, so that erasing everything cannot be a stray click.
    confirm: str = Field(max_length=32)


class ErasureResponse(BaseModel):
    receipt_id: uuid.UUID
    counts: dict[str, int]


class AdminResetCodeRequest(BaseModel):
    email: EmailStr
    # Also clear the second factor, for someone who has lost their authenticator
    # and their recovery codes. Off unless asked for.
    reset_mfa: bool = False


class AdminResetCodeResponse(BaseModel):
    code: str
    expires_at: datetime
    mfa_cleared: bool


class AdminErasureRequest(BaseModel):
    email: EmailStr
    admin_password: str = Field(min_length=1, max_length=72)
    mfa_code: str | None = Field(default=None, max_length=16)
    confirm: str = Field(max_length=32)


class RetentionRun(BaseModel):
    erased_conversations: int


class RetentionStatus(BaseModel):
    chat_retention_days: int
    chats_kept_until_deleted: bool
    conversations_past_retention: int


class PrivacyConfiguration(BaseModel):
    notice: dict[str, Any]
    data_fiduciary: str | None
    grievance: dict[str, Any]
    retention: dict[str, Any]
    self_service_reset: bool
