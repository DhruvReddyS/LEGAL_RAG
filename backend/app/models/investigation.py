"""Recorded dates for a police matter.

Kept off ``Case`` deliberately. A case is either a police matter or an
advocate's brief, and an advocate's brief has no arrest time, no remand date
and no inquest. Seven nullable columns on the shared table would be seven
columns that are always null for half the rows, and would invite reading a
null as a fact.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import OffenceGravity


class InvestigationFacts(Base):
    """One row per case, holding only what the deadline arithmetic reads.

    Every timestamp is nullable because a partially recorded investigation
    is the normal case, not an error. The calculation is built to say what
    it cannot determine, so an absent date produces an undetermined deadline
    rather than a refusal to compute anything.
    """

    __tablename__ = "investigation_facts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    information_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Not the arrest. The s.187(3) period runs from the first remand, and
    # computing it from the arrest shortens it -- which is why this is stored
    # as its own column rather than derived from arrested_at.
    first_remand_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accused_produced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    death_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preliminary_enquiry_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Defaults to unknown, never to a period. The column exists so that "we
    # did not record this" survives a round trip through the database as
    # itself rather than as sixty days.
    gravity: Mapped[OffenceGravity] = mapped_column(
        Enum(
            OffenceGravity,
            name="offence_gravity",
            # Store the value, not the member name. Without this SQLAlchemy
            # writes "UNKNOWN" into a type whose members are lowercase, which
            # every other enum column here already learned.
            values_callable=lambda enum_class: [item.value for item in enum_class],
        ),
        default=OffenceGravity.UNKNOWN,
        server_default=OffenceGravity.UNKNOWN.value,
        nullable=False,
    )
    is_listed_sexual_offence: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    is_unnatural_death: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    case: Mapped["Case"] = relationship(back_populates="investigation_facts")  # noqa: F821
