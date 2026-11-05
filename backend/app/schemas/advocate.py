from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import OffenceGravity
from app.services.bail import BailRoute
from app.schemas.plausible_dates import PlausibleDates


class BailAssessmentRequest(PlausibleDates):
    routes: list[BailRoute] = Field(default_factory=list)
    as_of: date | None = None
    offence_description: str | None = Field(default=None, max_length=2000)
    classification: Literal["bailable", "non_bailable", "unknown"] = "unknown"
    gravity: OffenceGravity = OffenceGravity.UNKNOWN
    punishable_with_death_or_life: bool | None = None
    max_punishment_months: int | None = Field(default=None, ge=0, le=1200)
    information_recorded_on: date | None = None
    arrested_on: date | None = None
    first_remand_on: date | None = None
    report_filed: bool | None = None
    report_filed_on: date | None = None
    in_custody: bool | None = None
    custody_started_on: date | None = None
    custody_days_before_current_spell: int = Field(default=0, ge=0, le=36500)
    delay_by_accused_days: int = Field(default=0, ge=0, le=36500)
    first_time_offender: bool | None = None
    other_cases_pending: bool | None = None
    previous_conviction_bar: bool | None = None
    child_woman_sick_or_infirm: bool | None = None
    involves_bns_65_or_70_2: bool | None = None
    triable_by_magistrate: bool | None = None
    first_evidence_date: date | None = None
    in_custody_whole_trial_period: bool | None = None
    include_authorities: bool = True
    save: bool = False


class DraftRequest(BaseModel):
    draft_type: str = Field(min_length=3, max_length=64)
    fields: dict[str, str] = Field(default_factory=dict)
    facts: str = Field(default="", max_length=12000)
    instructions: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _bounded_fields(self) -> "DraftRequest":
        if len(self.fields) > 30 or any(len(value) > 4000 for value in self.fields.values()):
            raise ValueError("Too much text in the form fields")
        return self


class CalendarEventCreate(PlausibleDates):
    kind: Literal["hearing", "limitation", "filing", "other"] = "hearing"
    title: str = Field(min_length=2, max_length=255)
    due_on: date
    notes: str | None = Field(default=None, max_length=4000)
    basis: dict = Field(default_factory=dict)


class CalendarEventUpdate(PlausibleDates):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    due_on: date | None = None
    notes: str | None = Field(default=None, max_length=4000)
    completed: bool | None = None


class LimitationRequest(PlausibleDates):
    article: str = Field(min_length=3, max_length=32)
    runs_from: date
    excluded_days: int = Field(default=0, ge=0, le=36500)
    add_to_calendar: bool = False
    title: str | None = Field(default=None, max_length=255)


class BriefRequest(BaseModel):
    kind: Literal["brief", "synopsis"] = "brief"
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    focus: str | None = Field(default=None, max_length=2000)


class PrecedentRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    holding: str | None = Field(default=None, max_length=1000)
    court: str | None = Field(default=None, max_length=255)
    year_from: int | None = Field(default=None, ge=1800, le=2100)
    year_to: int | None = Field(default=None, ge=1800, le=2100)


class TreatmentRequest(BaseModel):
    reference: str = Field(min_length=3, max_length=500)


class OpponentCheckRequest(BaseModel):
    text: str | None = Field(default=None, max_length=60000)
    document_id: uuid.UUID | None = None
    save: bool = False

    @model_validator(mode="after")
    def _one_input(self) -> "OpponentCheckRequest":
        if not (self.text or "").strip() and self.document_id is None:
            raise ValueError("Paste the filing, or choose a document from this case")
        return self


class ComparisonRequest(BaseModel):
    first_judgment_id: str = Field(min_length=3, max_length=128)
    second_judgment_id: str | None = Field(default=None, max_length=128)
    # The facts of this matter, as the second side of the comparison.
    matter_facts: str | None = Field(default=None, max_length=12000)
    focus: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _second_side(self) -> "ComparisonRequest":
        if not self.second_judgment_id and not (self.matter_facts or "").strip():
            raise ValueError("Choose a second judgment, or enter this matter's facts")
        if self.second_judgment_id and (self.matter_facts or "").strip():
            raise ValueError("Compare against a second judgment or this matter's facts, not both")
        return self


class DebateRequest(BaseModel):
    proposition: str = Field(min_length=10, max_length=2000)
    facts: str | None = Field(default=None, max_length=12000)
    rounds: int = Field(default=2, ge=1, le=3)
