"""What a citizen records for themselves, and what an answer was graded.

Both are new tables rather than new columns. Deadlines belong to one person
and carry their own private notes, so they never sit on a shared table. The
annotation exists because a chat message row stores neither its section grades
nor whether it was a safety intervention, so a reopened conversation had
nothing to show for either.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CitizenDeadline(Base):
    """A date the user wrote down for their own situation.

    The user owns the date. Nothing here asserts that a date is legally right;
    a row that came from a tool keeps the provision it was computed from, so
    the reader can always go back and check the basis.
    """

    __tablename__ = "citizen_deadlines"
    __table_args__ = (
        CheckConstraint(
            "remind_days_before >= 0 AND remind_days_before <= 90",
            name="ck_citizen_deadlines_remind_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    remind_days_before: Mapped[int] = mapped_column(Integer, nullable=False, default=7, server_default="7")
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual", server_default="manual")
    provision_label: Mapped[str | None] = mapped_column(String(160))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChatMessageAnnotation(Base):
    """Facts about a published answer that the message row does not hold."""

    __tablename__ = "chat_message_annotations"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    section_confidence: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    # "emergency" or "refusal" when the screen answered, instead of the corpus.
    safety_kind: Mapped[str | None] = mapped_column(String(32))
