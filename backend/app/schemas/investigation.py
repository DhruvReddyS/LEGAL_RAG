"""Request and response shapes for the investigation timeline.

Dates can be supplied inline for a what-if, or recorded against the case and
read back. Both paths run the same arithmetic.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import OffenceGravity
from app.services.investigation_compliance import ComplianceStatus, PoliceAction
from app.schemas.plausible_dates import PlausibleDates


class InvestigationTimelineRequest(PlausibleDates):
    """Whatever is known. Everything is optional on purpose.

    A partially recorded investigation is the normal case, and the
    calculation is built to say what it cannot determine rather than to
    require a complete record before it will answer at all.
    """

    information_recorded_at: datetime | None = None
    arrested_at: datetime | None = None
    first_remand_at: datetime | None = Field(
        default=None,
        description=(
            "Date of first remand. The s.187(3) default-bail period runs from "
            "this, not from the arrest. Without it the period is reported as "
            "undetermined rather than computed from the arrest date, which "
            "would shorten it."
        ),
    )
    accused_produced_at: datetime | None = None
    death_occurred_at: datetime | None = None
    gravity: OffenceGravity = Field(
        default=OffenceGravity.UNKNOWN,
        description=(
            "Whether the offence is punishable with death, life, or ten years "
            "or more. Left unknown, the s.187(3) period is not guessed."
        ),
    )
    is_listed_sexual_offence: bool = Field(
        default=False,
        description=(
            "True for BNS ss.64-68, 70, 71 and POCSO ss.4, 6, 8, 10, which carry "
            "the two-month completion rule in s.193(2). BNS s.69 is not listed."
        ),
    )
    is_rape_or_attempt: bool = Field(
        default=False,
        description=(
            "Rape or attempted rape of a woman. This, not the s.193(2) listing, "
            "is what brings s.184 into play."
        ),
    )
    victim_examined_at: datetime | None = None
    arrested_under_warrant: bool | None = Field(
        default=None,
        description="Chooses s.78 over s.58. Null means the arrest type is not recorded.",
    )
    police_report_forwarded_at: datetime | None = None
    special_statute: Literal["none", "ndps_s36a"] = Field(
        default="none",
        description=(
            "ndps_s36a stops the s.187(3) date being computed: NDPS Act s.36A(4) "
            "changes the period."
        ),
    )
    preliminary_enquiry_started_at: datetime | None = None
    is_unnatural_death: bool = False
    is_custodial_death: bool = False


class DeadlineResponse(BaseModel):
    key: str
    obligation: str
    provision: str
    due_at: datetime | None
    consequence: str
    computed_from: str
    is_earliest_possible: bool
    undetermined_because: str
    actor: str = "investigating_officer"
    notes: list[str] = Field(default_factory=list)
    is_breached: bool | None = Field(
        description=(
            "None where the deadline could not be computed. Never False for "
            "an undetermined deadline -- that would report compliance which "
            "was never established."
        )
    )


class InvestigationTimelineResponse(BaseModel):
    evaluated_at: datetime
    deadlines: list[DeadlineResponse]
    breached: list[str]
    undetermined: list[str]


class InvestigationFactsResponse(InvestigationTimelineRequest):
    """What is on record for this matter.

    Extends the request shape so that what you can send and what you get
    back cannot drift apart -- a stored field that the request cannot set
    is a field nobody can correct.
    """

    case_id: uuid.UUID
    updated_at: datetime


class ComplianceItemResponse(BaseModel):
    key: str
    requirement: str
    provision: str
    consequence: str
    status: ComplianceStatus
    applies_because: str


class ComplianceChecklistResponse(BaseModel):
    action: PoliceAction
    items: list[ComplianceItemResponse]
    # Positively not done. An item nobody has confirmed appears in
    # `not_recorded`, never here: an unknown is not a breach.
    outstanding: list[str]
    not_recorded: list[str]
    # What this checklist was computed with, so a reload can show the same list.
    flags: dict[str, bool] = Field(default_factory=dict)


class ComplianceUpdateRequest(BaseModel):
    """What has been confirmed, one way or the other.

    Replaces the statuses of the rows the effective flags list. A listed key
    absent from the map returns to not_recorded, which is how a wrongly ticked
    item is unticked. Rows the flags do not list keep what they had.
    """

    action: PoliceAction
    status: dict[str, ComplianceStatus] = Field(default_factory=dict)
    # Null keeps what is stored. These decide which conditional rows are listed,
    # so they are part of the record: a reload must show the same list.
    arrested_person_is_woman: bool | None = None
    handcuffs_used: bool | None = None
    memorandum_attested_by_family: bool | None = None
    bailable_arrest_without_warrant: bool | None = None
    # s.193(3)(i)(h) and (i): both conditional, both new in the BNSS.
    is_listed_sexual_offence: bool | None = None
    electronic_device_seized: bool | None = None
