"""Account recovery, device sessions, consent and server-side history metadata.

New tables rather than new columns on ``users`` and ``chat_sessions``: a TOTP
secret has no business being selected every time a user row is loaded, and
everything here goes when its user does, by the foreign key.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserSecurity(Base):
    """One row per user who has touched password recovery or a second factor."""

    __tablename__ = "user_security"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # Encrypted, because a verifier has to recover the secret to compute a code;
    # a hash would not work here the way it does for a password.
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    # Null while enrolling. A secret only counts once a code has proved the
    # authenticator actually holds it, or a typo would lock the account.
    totp_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The newest accepted time step, so a code read over a shoulder cannot be
    # replayed inside its 30-second window.
    totp_last_step: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0"), default=0
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordResetCode(Base):
    """A one-time code. Only its hash is stored."""

    __tablename__ = "password_reset_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # The administrator who issued it, or null when it was sent by mail on the
    # person's own request.
    issued_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserSession(Base):
    """One signed-in device.

    Holds a readable label and timestamps and nothing else: no raw user agent
    and no IP address. Enough for someone to recognise their own devices, and
    no more than that is worth keeping about them.
    """

    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_user_revoked", "user_id", "revoked_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConsentRecord(Base):
    """One row per acceptance. A later version is a new row; history stays."""

    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    notice_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ErasureReceipt(Base):
    """Proof that an erasure happened, deliberately naming nobody.

    The id is handed to the person so they can quote it. Holding their email or
    a hash of it here would keep the very record they asked to have removed.
    """

    __tablename__ = "erasure_receipts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    erased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    initiated_by: Mapped[str] = mapped_column(String(16), nullable=False)
    counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


class ChatSessionMeta(Base):
    """How a person has organised a conversation: pinned, and which matter."""

    __tablename__ = "chat_session_meta"
    __table_args__ = (
        Index("ix_chat_session_meta_user_pinned", "user_id", "pinned_at"),
        Index("ix_chat_session_meta_user_matter", "user_id", "matter"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    matter: Mapped[str | None] = mapped_column(String(120))
