from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ChatMessageRole, FeedbackRating


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="SET NULL"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="chat_sessions")
    case: Mapped[Case | None] = relationship(back_populates="chat_sessions")
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        # Insert order, not the timestamp. `created_at` defaults to `now()`,
        # which in PostgreSQL is the transaction timestamp, and a chat request
        # writes the question and the answer in one transaction -- so both
        # rows carried an identical value and this ordering was left to the
        # planner. Measured: 1,225 of 2,912 stored messages shared a timestamp
        # with a sibling, and a citizen could be shown the answer above the
        # question.
        order_by="ChatMessage.sequence",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="confidence_score_range",
        ),
        # Every read of a conversation is "this session, in order".
        Index("ix_chat_messages_session_id_sequence", "session_id", "sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Monotonic, server-assigned, and the only correct way to order a
    # conversation. The primary key is a random UUID, so it cannot break a
    # timestamp tie, and the timestamp ties constantly -- see the note on
    # ChatSession.messages. Assigned by a sequence rather than a finer clock
    # because an integer cannot tie at all.
    sequence: Mapped[int] = mapped_column(
        BigInteger,
        Sequence("chat_messages_sequence_seq"),
        nullable=False,
        server_default=text("nextval('chat_messages_sequence_seq')"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[ChatMessageRole] = mapped_column(
        Enum(
            ChatMessageRole,
            name="chat_message_role",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")
    feedback: Mapped[list[Feedback]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_feedback_message_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    rating: Mapped[FeedbackRating] = mapped_column(
        Enum(
            FeedbackRating,
            name="feedback_rating",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
    )
    correction_text: Mapped[str | None] = mapped_column(Text)

    message: Mapped[ChatMessage] = relationship(back_populates="feedback")
    user: Mapped[User] = relationship(back_populates="feedback")
