"""The working record of a police investigation.

Everything here hangs off a case and dies with it, except the supervision tables,
which name people rather than matters. Nothing here is reachable except through a
case the caller owns, and a supervisor's view is computed from these rows without
exposing them.

Custody and diary rows are append-only by design. A chain of custody whose entries
can be rewritten proves nothing, so a mistake is corrected by a new entry that names
the one it corrects.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _case_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), index=True, nullable=False
    )


def _user_fk() -> Mapped[uuid.UUID | None]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PoliceSearch(Base):
    """One search or seizure operation, and what is on record about it."""

    __tablename__ = "police_searches"

    id: Mapped[uuid.UUID] = _pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    place: Mapped[str] = mapped_column(Text, nullable=False)
    # warrant | section_185 | unknown
    basis: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unknown")
    searched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grounds_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_sent_to_magistrate_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recording_forwarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    witness_count: Mapped[int | None] = mapped_column(Integer)
    # Check key -> yes | no | unknown. Absent is unknown; it never reads as yes.
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PoliceEvidenceItem(Base):
    __tablename__ = "police_evidence_items"
    __table_args__ = (UniqueConstraint("case_id", "exhibit_label", name="uq_police_exhibit_label"),)

    id: Mapped[uuid.UUID] = _pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    exhibit_label: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # physical | document | electronic | biological | other
    category: Mapped[str] = mapped_column(String(20), nullable=False, server_default="physical")
    seized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seized_from: Mapped[str | None] = mapped_column(Text)
    seized_by: Mapped[str | None] = mapped_column(String(255))
    search_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("police_searches.id", ondelete="SET NULL")
    )
    # held | sent_for_examination | produced_in_court | returned | entered_in_error
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="held")
    storage_location: Mapped[str | None] = mapped_column(Text)
    digital_hash: Mapped[str | None] = mapped_column(String(255))
    # yes | no | unknown. BSA s.63(4), for an electronic record.
    certificate_s63: Mapped[str] = mapped_column(String(10), nullable=False, server_default="unknown")
    reported_to_magistrate_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PoliceCustodyEvent(Base):
    """One hand-over. Append-only: no route updates or deletes these."""

    __tablename__ = "police_custody_events"

    id: Mapped[uuid.UUID] = _pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("police_evidence_items.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    from_person: Mapped[str] = mapped_column(String(255), nullable=False)
    to_person: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text)
    place: Mapped[str | None] = mapped_column(Text)
    # A later entry that replaces an earlier one. The earlier one stays visible.
    corrects_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("police_custody_events.id", ondelete="SET NULL")
    )
    recorded_by: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = _created()


class PoliceWitness(Base):
    __tablename__ = "police_witnesses"

    id: Mapped[uuid.UUID] = _pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # complainant | victim | eyewitness | search_witness | expert | official | other
    category: Mapped[str] = mapped_column(String(30), nullable=False, server_default="other")
    contact: Mapped[str | None] = mapped_column(Text)
    # s.179(1) proviso: may not be required to attend anywhere but home.
    attends_only_at_residence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # s.180(3) second proviso: the statement is recorded by a woman officer.
    needs_woman_officer: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    statement_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # written | audio_video
    statement_mode: Mapped[str | None] = mapped_column(String(20))
    # yes | no | unknown
    recorded_by_woman_officer: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="unknown"
    )
    inserted_in_diary: Mapped[str] = mapped_column(String(10), nullable=False, server_default="unknown")
    magistrate_statement_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bond_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # to_be_examined | examined | unavailable | dropped | entered_in_error
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="to_be_examined")
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PoliceDeadlineCompletion(Base):
    """When a statutory step was actually taken. A deadline without one is open."""

    __tablename__ = "police_deadline_completions"
    __table_args__ = (UniqueConstraint("case_id", "deadline_key", name="uq_police_deadline_done"),)

    id: Mapped[uuid.UUID] = _pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    deadline_key: Mapped[str] = mapped_column(String(120), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = _created()


class PoliceComplianceRecord(Base):
    """The date and the evidence behind a duty. Its status stays on the checklist."""

    __tablename__ = "police_compliance_records"
    __table_args__ = (
        UniqueConstraint("case_id", "action", "requirement_key", name="uq_police_compliance_record"),
    )

    id: Mapped[uuid.UUID] = _pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    requirement_key: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_note: Mapped[str | None] = mapped_column(Text)
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("police_evidence_items.id", ondelete="SET NULL")
    )
    recorded_by: Mapped[uuid.UUID | None] = _user_fk()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PoliceOffenceAssessment(Base):
    __tablename__ = "police_offence_assessments"
    __table_args__ = (UniqueConstraint("case_id", "offence_key", name="uq_police_offence_assessment"),)

    id: Mapped[uuid.UUID] = _pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    offence_key: Mapped[str] = mapped_column(String(60), nullable=False)
    # Element key -> {state, evidence_item_ids, witness_ids, note}.
    elements: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    recorded_by: Mapped[uuid.UUID | None] = _user_fk()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PoliceRemandPeriod(Base):
    """One period of authorised custody, as the order states it."""

    __tablename__ = "police_remand_periods"

    id: Mapped[uuid.UUID] = _pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    # police | judicial
    custody_type: Mapped[str] = mapped_column(String(10), nullable=False)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    magistrate: Mapped[str | None] = mapped_column(String(255))
    order_reference: Mapped[str | None] = mapped_column(String(255))
    recorded_by: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = _created()


class PoliceDiaryEntry(Base):
    """A page of the case diary. Append-only, and numbered by the server."""

    __tablename__ = "police_diary_entries"
    __table_args__ = (UniqueConstraint("case_id", "page_no", name="uq_police_diary_page"),)

    id: Mapped[uuid.UUID] = _pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    information_reached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    began_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    places_visited: Mapped[str | None] = mapped_column(Text)
    circumstances: Mapped[str] = mapped_column(Text, nullable=False)
    statements_inserted: Mapped[str | None] = mapped_column(Text)
    corrects_page: Mapped[int | None] = mapped_column(Integer)
    recorded_by: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = _created()


class PoliceUnit(Base):
    """A group of officers. Only an administrator creates one or changes who is in it."""

    __tablename__ = "police_units"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = _created()


class PoliceUnitMember(Base):
    """Membership, and the explicit grant a supervisor's view rests on."""

    __tablename__ = "police_unit_members"
    __table_args__ = (UniqueConstraint("unit_id", "user_id", name="uq_police_unit_member"),)

    id: Mapped[uuid.UUID] = _pk()
    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("police_units.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # member | supervisor
    role: Mapped[str] = mapped_column(String(12), nullable=False, server_default="member")
    added_by: Mapped[uuid.UUID | None] = _user_fk()
    added_at: Mapped[datetime] = _created()
