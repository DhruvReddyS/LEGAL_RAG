from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, false, func, true
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import CorpusSourceType


class CorpusSource(Base):
    __tablename__ = "corpus_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[CorpusSourceType] = mapped_column(
        Enum(
            CorpusSourceType,
            name="corpus_source_type",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        index=True,
        nullable=False,
    )
    jurisdiction: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    court: Mapped[str | None] = mapped_column(String(255))
    date_enacted: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=true(), index=True, nullable=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_sources.id", ondelete="SET NULL"),
    )

    superseding_source: Mapped[CorpusSource | None] = relationship(
        remote_side="CorpusSource.id",
        back_populates="superseded_sources",
    )
    superseded_sources: Mapped[list[CorpusSource]] = relationship(
        back_populates="superseding_source",
    )
    bookmarks: Mapped[list[Bookmark]] = relationship(
        back_populates="corpus_source",
        cascade="all, delete-orphan",
    )


class Bookmark(Base):
    __tablename__ = "bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "corpus_source_id", name="uq_bookmark_user_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    corpus_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_sources.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    notify_on_amendment: Mapped[bool] = mapped_column(
        Boolean,
        server_default=false(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="bookmarks")
    corpus_source: Mapped[CorpusSource] = relationship(back_populates="bookmarks")


class CorpusIntake(Base):
    __tablename__ = "corpus_intakes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    storage_object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("storage_objects.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    corpus_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_sources.id", ondelete="SET NULL"),
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[CorpusSourceType] = mapped_column(
        Enum(
            CorpusSourceType,
            name="corpus_source_type",
            values_callable=lambda enum_class: [item.value for item in enum_class],
            create_type=False,
        ),
        nullable=False,
    )
    jurisdiction: Mapped[str] = mapped_column(String(255), nullable=False)
    authority: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), server_default="staged", index=True, nullable=False)
    validation_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
