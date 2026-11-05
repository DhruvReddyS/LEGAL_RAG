"""What keeping the corpus current leaves behind.

A notice belongs to one person and goes with their account or conversation. A
review item holds an answer with its identifiers removed, and cascades from the
message it was drawn from, so erasing a conversation also erases its review.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocumentCurrencyState(Base):
    """The currency last seen for a document, which is how a change is noticed."""

    __tablename__ = "document_currency_states"

    canonical_document_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    superseded_by: Mapped[str | None] = mapped_column(String(500))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LawChangeNotice(Base):
    """A saved answer of this person's relied on a law whose status has changed."""

    __tablename__ = "law_change_notices"
    __table_args__ = (
        UniqueConstraint("message_id", "change_key", name="uq_law_change_notice_message_change"),
        Index("ix_law_change_notices_user_read", "user_id", "read_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    canonical_document_id: Mapped[str] = mapped_column(String(128), nullable=False)
    document_title: Mapped[str] = mapped_column(String(500), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(16), nullable=False)
    current_status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Each copied from the curated currency decision. Never written by a model.
    superseded_by: Mapped[str | None] = mapped_column(String(500))
    effective: Mapped[str | None] = mapped_column(String(32))
    basis: Mapped[str | None] = mapped_column(Text)
    change_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AmendmentFindingReview(Base):
    """An administrator's answer to one finding from the amendment check.

    The findings are a file so the check can run with no database. Keyed by a hash
    of what was found, so the same finding stays answered across runs and a new
    observation is a new finding.
    """

    __tablename__ = "amendment_finding_reviews"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'reviewed', 'dismissed')", name="status_valid"),
    )

    finding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ExpertReviewItem(Base):
    """One sampled answer, with its identifiers already removed.

    `message_id` exists so a conversation's erasure reaches this row and an answer is
    not sampled twice. No route returns it. Nothing else about who asked is stored,
    and the date is kept to the month.
    """

    __tablename__ = "expert_review_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_messages.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    answered_month: Mapped[str] = mapped_column(String(7), nullable=False)
    citations: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    sampled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )


class ExpertReviewClaim(Base):
    __tablename__ = "expert_review_claims"
    __table_args__ = (
        UniqueConstraint("item_id", "ordinal", name="uq_expert_review_claim_ordinal"),
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('correct', 'incorrect', 'unsure')", name="verdict_valid"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expert_review_items.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
