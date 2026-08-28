from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class StorageNamespace(StrEnum):
    LEGAL_CORPUS = "legal_corpus"
    POLICE_CASE = "police_case"
    ADVOCATE_CASE = "advocate_case"
    GENERATED_DOCUMENT = "generated_document"


class StorageObject(Base):
    __tablename__ = "storage_objects"
    __table_args__ = (
        UniqueConstraint("bucket", "object_key", name="uq_storage_bucket_object_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    namespace: Mapped[StorageNamespace] = mapped_column(
        Enum(
            StorageNamespace,
            name="storage_namespace",
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        index=True,
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    owner: Mapped[User | None] = relationship(back_populates="storage_objects")
    case: Mapped[Case | None] = relationship(back_populates="storage_objects")
