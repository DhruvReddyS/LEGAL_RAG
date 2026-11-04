"""State the administration console keeps for itself.

Everything here is about operating the system. Nothing holds a user's question
or evidence text: free-text columns are written by an administrator, and the
audit rows that accompany them record only that a note exists.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReleaseDecision(Base):
    """An administrator approving or refusing a corpus cutover.

    Keeps the gate results it was decided on, so a later reader sees what was in
    front of them rather than whatever the evidence directory says today.
    """

    __tablename__ = "release_decisions"
    __table_args__ = (
        CheckConstraint("decision IN ('approve', 'refuse')", name="decision_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    collection: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    override_failed_gates: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    gate_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )


class GateRun(Base):
    """A queued run of the corpus gates, executed outside the API process."""

    __tablename__ = "gate_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'failed', 'cancelled')",
            name="status_valid",
        ),
        # At most one run waiting or running. The gates are measurements of an
        # idle machine, so two at once would invalidate both.
        Index(
            "uq_gate_runs_one_active",
            text("(1)"),
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    collection: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", server_default="queued")
    exit_code: Mapped[int | None] = mapped_column(Integer)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentQuarantine(Base):
    """A corpus document withheld from retrieval during an incident.

    Source of truth for the exclusion. It outlives a collection cutover, which a
    flag written into the vector payload would not.
    """

    __tablename__ = "document_quarantines"
    __table_args__ = (
        Index(
            "uq_document_quarantines_one_active",
            "canonical_document_id",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_document_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    feedback_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feedback.id", ondelete="SET NULL")
    )
    quarantined_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    quarantined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    release_reason: Mapped[str | None] = mapped_column(Text)


class FeedbackTriage(Base):
    __tablename__ = "feedback_triage"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'investigating', 'resolved', 'dismissed')",
            name="status_valid",
        ),
    )

    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feedback.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", server_default="open")
    note: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AccountFlag(Base):
    """Administrative requirements on an account.

    `force_password_reset` and `mfa_required` are set here. Sign-in reads them
    through `app.services.admin_users.account_flags_for`.
    """

    __tablename__ = "account_flags"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    force_password_reset: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    mfa_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    suspended_reason: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RetentionPolicy(Base):
    """How long one category of data is kept. Null days means keep it."""

    __tablename__ = "retention_policies"

    category: Mapped[str] = mapped_column(String(32), primary_key=True)
    days: Mapped[int | None] = mapped_column(Integer)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RetentionRun(Base):
    """A dry run, or the purge that consumed one."""

    __tablename__ = "retention_runs"
    __table_args__ = (
        CheckConstraint("kind IN ('dry_run', 'purge')", name="kind_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    dry_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retention_runs.id", ondelete="SET NULL"), unique=True
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    cutoffs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )


class CorpusWorkItem(Base):
    """Where one document stands on an OCR, verification or currency work list."""

    __tablename__ = "corpus_work_items"
    __table_args__ = (
        UniqueConstraint("canonical_document_id", "queue", name="uq_corpus_work_item"),
        CheckConstraint("queue IN ('ocr', 'verification', 'currency')", name="queue_valid"),
        CheckConstraint("status IN ('open', 'in_progress', 'done')", name="status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_document_id: Mapped[str] = mapped_column(String(128), nullable=False)
    queue: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", server_default="open")
    note: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
