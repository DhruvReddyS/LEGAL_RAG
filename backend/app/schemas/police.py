"""Request and response shapes for the police working record.

Times must carry an offset. A naive time on a custody entry is a time nobody can place,
and these rows are read by people deciding whether something happened within a limit.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.services.investigation_compliance import ComplianceStatus, PoliceAction
from app.services.police_offences import ElementState
from app.schemas.plausible_dates import PlausibleDates

TriState = Literal["yes", "no", "unknown"]


class _Row(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Deadline register


class RegisterRowResponse(BaseModel):
    case_id: uuid.UUID
    case_title: str
    key: str
    obligation: str
    provision: str
    actor: str
    is_officer_duty: bool
    consequence: str
    computed_from: str
    due_at: datetime | None
    state: Literal["breached", "overdue", "due", "met", "unknown"]
    state_reason: str
    is_earliest_possible: bool
    is_imminent: bool
    completed_at: datetime | None
    completion_note: str
    completion_is_derived: bool
    notes: list[str]


class CaseReference(BaseModel):
    case_id: uuid.UUID
    title: str


class RegisterResponse(BaseModel):
    evaluated_at: datetime
    imminent_hours: int
    rows: list[RegisterRowResponse]
    # Counted over the rows the filters left, officer's own duties only.
    counts: dict[str, int]
    # A case with nothing recorded is unknown, not fine, so it stays visible.
    cases_without_facts: list[CaseReference]


class CompletionRequest(PlausibleDates):
    completed_at: AwareDatetime
    note: str | None = Field(default=None, max_length=2000)


# ---- Compliance as a record


class ComplianceRecordRequest(PlausibleDates):
    status: ComplianceStatus | None = None
    occurred_at: AwareDatetime | None = None
    evidence_note: str | None = Field(default=None, max_length=4000)
    evidence_item_id: uuid.UUID | None = None


class ComplianceRecordItem(BaseModel):
    key: str
    requirement: str
    provision: str
    consequence: str
    applies_because: str
    status: ComplianceStatus
    occurred_at: datetime | None = None
    evidence_note: str | None = None
    evidence_item_id: uuid.UUID | None = None
    evidence_label: str | None = None
    # Marked done, with neither a date nor anything to show for it.
    needs_record: bool = False


class ComplianceRecordResponse(BaseModel):
    action: PoliceAction
    items: list[ComplianceRecordItem]
    flags: dict[str, bool]


# ---- Evidence and custody

EvidenceCategory = Literal["physical", "document", "electronic", "biological", "other"]
EvidenceStatus = Literal["held", "sent_for_examination", "produced_in_court", "returned", "entered_in_error"]


class EvidenceCreate(PlausibleDates):
    exhibit_label: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=3, max_length=4000)
    category: EvidenceCategory = "physical"
    seized_at: AwareDatetime | None = None
    seized_from: str | None = Field(default=None, max_length=2000)
    seized_by: str | None = Field(default=None, max_length=255)
    search_id: uuid.UUID | None = None
    status: EvidenceStatus = "held"
    storage_location: str | None = Field(default=None, max_length=2000)
    digital_hash: str | None = Field(default=None, max_length=255)
    certificate_s63: TriState = "unknown"
    reported_to_magistrate_at: AwareDatetime | None = None
    notes: str | None = Field(default=None, max_length=4000)


class EvidenceUpdate(PlausibleDates):
    description: str | None = Field(default=None, min_length=3, max_length=4000)
    category: EvidenceCategory | None = None
    seized_at: AwareDatetime | None = None
    seized_from: str | None = Field(default=None, max_length=2000)
    seized_by: str | None = Field(default=None, max_length=255)
    search_id: uuid.UUID | None = None
    status: EvidenceStatus | None = None
    storage_location: str | None = Field(default=None, max_length=2000)
    digital_hash: str | None = Field(default=None, max_length=255)
    certificate_s63: TriState | None = None
    reported_to_magistrate_at: AwareDatetime | None = None
    notes: str | None = Field(default=None, max_length=4000)


class CustodyEventCreate(PlausibleDates):
    occurred_at: AwareDatetime
    from_person: str = Field(min_length=2, max_length=255)
    to_person: str = Field(min_length=2, max_length=255)
    purpose: str | None = Field(default=None, max_length=2000)
    place: str | None = Field(default=None, max_length=2000)
    corrects_event_id: uuid.UUID | None = None


class CustodyEventResponse(_Row):
    id: uuid.UUID
    occurred_at: datetime
    from_person: str
    to_person: str
    purpose: str | None
    place: str | None
    corrects_event_id: uuid.UUID | None
    created_at: datetime


class ChainResponse(BaseModel):
    state: Literal["continuous", "broken", "cannot_be_determined"]
    current_holder: str | None
    issues: list[str]


class EvidenceResponse(_Row):
    id: uuid.UUID
    case_id: uuid.UUID
    exhibit_label: str
    description: str
    category: str
    seized_at: datetime | None
    seized_from: str | None
    seized_by: str | None
    search_id: uuid.UUID | None
    status: str
    storage_location: str | None
    digital_hash: str | None
    certificate_s63: str
    reported_to_magistrate_at: datetime | None
    notes: str | None
    created_at: datetime
    custody_events: list[CustodyEventResponse] = Field(default_factory=list)
    chain: ChainResponse | None = None


class EvidenceListResponse(BaseModel):
    items: list[EvidenceResponse]


# ---- Witnesses

WitnessCategory = Literal["complainant", "victim", "eyewitness", "search_witness", "expert", "official", "other"]
WitnessStatus = Literal["to_be_examined", "examined", "unavailable", "dropped", "entered_in_error"]


class WitnessCreate(PlausibleDates):
    name: str = Field(min_length=2, max_length=255)
    category: WitnessCategory = "other"
    contact: str | None = Field(default=None, max_length=2000)
    attends_only_at_residence: bool = False
    needs_woman_officer: bool = False
    statement_recorded_at: AwareDatetime | None = None
    statement_mode: Literal["written", "audio_video"] | None = None
    recorded_by_woman_officer: TriState = "unknown"
    inserted_in_diary: TriState = "unknown"
    magistrate_statement_at: AwareDatetime | None = None
    bond_executed_at: AwareDatetime | None = None
    status: WitnessStatus = "to_be_examined"
    notes: str | None = Field(default=None, max_length=4000)


class WitnessUpdate(PlausibleDates):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    category: WitnessCategory | None = None
    contact: str | None = Field(default=None, max_length=2000)
    attends_only_at_residence: bool | None = None
    needs_woman_officer: bool | None = None
    statement_recorded_at: AwareDatetime | None = None
    statement_mode: Literal["written", "audio_video"] | None = None
    recorded_by_woman_officer: TriState | None = None
    inserted_in_diary: TriState | None = None
    magistrate_statement_at: AwareDatetime | None = None
    bond_executed_at: AwareDatetime | None = None
    status: WitnessStatus | None = None
    notes: str | None = Field(default=None, max_length=4000)


class WitnessDuty(BaseModel):
    key: str
    duty: str
    provision: str
    state: Literal["done", "not_done", "cannot_be_determined"]


class WitnessResponse(_Row):
    id: uuid.UUID
    case_id: uuid.UUID
    name: str
    category: str
    contact: str | None
    attends_only_at_residence: bool
    needs_woman_officer: bool
    statement_recorded_at: datetime | None
    statement_mode: str | None
    recorded_by_woman_officer: str
    inserted_in_diary: str
    magistrate_statement_at: datetime | None
    bond_executed_at: datetime | None
    status: str
    notes: str | None
    duties: list[WitnessDuty] = Field(default_factory=list)


class WitnessListResponse(BaseModel):
    witnesses: list[WitnessResponse]


# ---- Searches


class SearchWrite(PlausibleDates):
    place: str = Field(min_length=2, max_length=2000)
    basis: Literal["warrant", "section_185", "unknown"] = "unknown"
    searched_at: AwareDatetime | None = None
    grounds_recorded_at: AwareDatetime | None = None
    record_sent_to_magistrate_at: AwareDatetime | None = None
    recording_forwarded_at: AwareDatetime | None = None
    witness_count: int | None = Field(default=None, ge=0, le=500)
    answers: dict[str, TriState] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=4000)


class SearchCheckResponse(BaseModel):
    key: str
    requirement: str
    provision: str
    verdict: Literal["met", "not_met", "cannot_be_determined", "not_applicable"]
    detail: str


class SearchResponse(_Row):
    id: uuid.UUID
    case_id: uuid.UUID
    place: str
    basis: str
    searched_at: datetime | None
    grounds_recorded_at: datetime | None
    record_sent_to_magistrate_at: datetime | None
    recording_forwarded_at: datetime | None
    witness_count: int | None
    answers: dict[str, str]
    notes: str | None
    finding: str = "incomplete_record"
    counts: dict[str, int] = Field(default_factory=dict)
    checks: list[SearchCheckResponse] = Field(default_factory=list)


class SearchListResponse(BaseModel):
    searches: list[SearchResponse]


# ---- Offence elements


class ElementWrite(BaseModel):
    state: ElementState = ElementState.CANNOT_BE_DETERMINED
    evidence_item_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    witness_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    note: str | None = Field(default=None, max_length=4000)


class OffenceAssessmentWrite(BaseModel):
    elements: dict[str, ElementWrite] = Field(default_factory=dict)


class ElementResponse(BaseModel):
    key: str
    element: str
    provision: str
    source_quote: str
    state: ElementState
    evidence_item_ids: list[uuid.UUID]
    witness_ids: list[uuid.UUID]
    note: str


class OffenceAssessmentResponse(BaseModel):
    offence_key: str
    title: str
    provision: str
    limits: str
    finding: Literal["all_elements_supported", "element_not_established", "cannot_be_determined"]
    elements: list[ElementResponse]


class OffenceAssessmentList(BaseModel):
    assessments: list[OffenceAssessmentResponse]


class OffenceCatalogueEntry(BaseModel):
    key: str
    title: str
    provision: str
    limits: str
    element_count: int


class OffenceCatalogue(BaseModel):
    offences: list[OffenceCatalogueEntry]


# ---- Remand


class RemandCreate(PlausibleDates):
    custody_type: Literal["police", "judicial"]
    from_date: date
    to_date: date
    magistrate: str | None = Field(default=None, max_length=255)
    order_reference: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _ordered(self) -> "RemandCreate":
        if self.to_date < self.from_date:
            raise ValueError("The period cannot end before it starts")
        return self


class RemandPeriodResponse(_Row):
    id: uuid.UUID
    custody_type: str
    from_date: date
    to_date: date
    magistrate: str | None
    order_reference: str | None


class RemandResponse(BaseModel):
    periods: list[RemandPeriodResponse]
    police_days_used: int
    police_days_left: int
    judicial_days: int
    first_remand_date: date | None
    police_custody_window_ends: date | None
    window_days: int | None
    undetermined_because: str
    findings: list[str]
    provision: str = "BNSS s.187(2)"


# ---- Diary


class DiaryCreate(PlausibleDates):
    entry_date: date
    information_reached_at: AwareDatetime | None = None
    began_at: AwareDatetime | None = None
    closed_at: AwareDatetime | None = None
    places_visited: str | None = Field(default=None, max_length=4000)
    circumstances: str = Field(min_length=3, max_length=20000)
    statements_inserted: str | None = Field(default=None, max_length=4000)
    corrects_page: int | None = Field(default=None, ge=1)


class DiaryEntryResponse(_Row):
    id: uuid.UUID
    page_no: int
    entry_date: date
    information_reached_at: datetime | None
    began_at: datetime | None
    closed_at: datetime | None
    places_visited: str | None
    circumstances: str
    statements_inserted: str | None
    corrects_page: int | None
    created_at: datetime


class DiaryResponse(BaseModel):
    entries: list[DiaryEntryResponse]
    # Days since the first entry with no entry. Not a finding of lapse.
    days_without_entry: list[date]


# ---- Drafts


class DraftCreate(BaseModel):
    draft_type: Literal[
        "s35_3_notice",
        "s94_production_order",
        "seizure_memo",
        "case_diary_entry",
        "remand_application",
        "chargesheet_skeleton",
    ]
    inputs: dict[str, str | int | bool | None] = Field(default_factory=dict)


class DraftSummary(BaseModel):
    id: uuid.UUID
    draft_type: str
    title: str
    version: int
    status: str
    missing_field_count: int
    created_at: datetime


class DraftListResponse(BaseModel):
    drafts: list[DraftSummary]


class DraftResponse(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    draft_type: str
    title: str
    version: int
    status: str
    rendered_text: str
    missing_fields: list[str]
    provisions: list[str]
    disclaimer: str
    inputs: dict
    created_at: datetime


# ---- Case file


class CaseFileResponse(BaseModel):
    case_id: uuid.UUID
    generated_at: datetime
    included_witness_contact: bool
    html: str
    missing_sections: list[str]


class AccessEntry(BaseModel):
    at: datetime
    who: str
    what: str


class AccessLogResponse(BaseModel):
    entries: list[AccessEntry]


# ---- Units and supervision


class UnitCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class UnitMemberWrite(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal["member", "supervisor"] = "member"


class UnitMemberResponse(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: str


class UnitResponse(BaseModel):
    id: uuid.UUID
    name: str
    members: list[UnitMemberResponse]


class UnitListResponse(BaseModel):
    units: list[UnitResponse]


class MyUnitEntry(BaseModel):
    unit_id: uuid.UUID
    unit_name: str
    my_role: str
    supervisors: list[str]


class MyUnitsResponse(BaseModel):
    units: list[MyUnitEntry]


class SupervisedDeadline(BaseModel):
    key: str
    obligation: str
    provision: str
    actor: str
    due_at: datetime | None
    state: str
    state_reason: str
    is_imminent: bool


class SupervisedCase(BaseModel):
    case_id: uuid.UUID
    title: str
    officer_name: str
    has_facts: bool
    counts: dict[str, int]
    compliance: dict[str, int]
    attention: list[SupervisedDeadline]


class SupervisedUnitResponse(BaseModel):
    unit_id: uuid.UUID
    unit_name: str
    evaluated_at: datetime
    imminent_hours: int
    officer_count: int
    counts: dict[str, int]
    compliance: dict[str, int]
    cases: list[SupervisedCase]
