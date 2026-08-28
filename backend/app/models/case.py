from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import CaseRoleType


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    role_type: Mapped[CaseRoleType] = mapped_column(
        Enum(
            CaseRoleType,
            name="case_role_type",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    owner: Mapped[User] = relationship(back_populates="cases")
    documents: Mapped[list[CaseDocument]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
    chat_sessions: Mapped[list[ChatSession]] = relationship(back_populates="case")
    generated_documents: Mapped[list[GeneratedDocument]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
    storage_objects: Mapped[list[StorageObject]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )


class CaseDocument(Base):
    __tablename__ = "case_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(100), nullable=False)
    ocr_text: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    case: Mapped[Case] = relationship(back_populates="documents")


class GeneratedDocument(Base):
    __tablename__ = "documents_generated"
    __table_args__ = (
        UniqueConstraint("case_id", "doc_type", "version", name="uq_generated_case_type_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    doc_type: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    case: Mapped[Case] = relationship(back_populates="generated_documents")
