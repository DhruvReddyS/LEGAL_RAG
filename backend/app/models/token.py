from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RevokedRefreshToken(Base):
    """A refresh token that must no longer be accepted.

    Refresh tokens previously stayed valid for their full seven days no matter
    what: rotation issued a new pair without invalidating the old one, and
    logout only cleared a cookie, which is an instruction to the browser and
    not a revocation. A token captured from a shared machine survived sign-out
    for a week, and an administrator had no way to end a session.

    Rows are keyed on the token's `jti`. `expires_at` is stored so the table
    can be swept: a revoked token that has expired on its own is no longer
    worth remembering.
    """

    __tablename__ = "revoked_refresh_tokens"
    __table_args__ = (
        Index("ix_revoked_refresh_tokens_expires_at", "expires_at"),
    )

    jti: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # "rotated", "logout", or "reuse_detected". Kept for the audit trail: a
    # reuse detection is a security event, a logout is routine.
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
