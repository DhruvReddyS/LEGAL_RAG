"""Request and response shapes for the investigation timeline.

Dates can be supplied inline for a what-if, or recorded against the case and
read back. Both paths run the same arithmetic.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import OffenceGravity


class InvestigationTimelineRequest(BaseModel):
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
            "True for BNS ss.64-71 and POCSO ss.4, 6, 8, 10, which carry the "
            "two-month completion rule in s.193(2)."
        ),
    )
    preliminary_enquiry_started_at: datetime | None = None
    is_unnatural_death: bool = False


class DeadlineResponse(BaseModel):
    key: str
    obligation: str
    provision: str
    due_at: datetime | None
    consequence: str
    computed_from: str
    is_earliest_possible: bool
    undetermined_because: str
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
