from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FIRFacts(BaseModel):
    complainant_name: str | None = Field(default=None, description="Explicitly stated complainant name")
    complainant_contact: str | None = Field(default=None, description="Explicit phone, address or contact details")
    incident_date: str | None = Field(default=None, description="Explicit incident or last-seen date")
    incident_time: str | None = Field(default=None, description="Explicit incident or last-seen time")
    incident_location: str | None = Field(default=None, description="Explicit incident or last-seen place")
    subject_or_property: str | None = Field(
        default=None,
        description="Person, animal or property missing, lost, stolen, damaged or involved; include its stated name/type",
    )
    suspected_offence_or_circumstance: str | None = Field(
        default=None,
        description="Only a circumstance or offence explicitly alleged; preserve uncertainty such as theft not witnessed",
    )
    suspect_details: str | None = Field(default=None, description="Only explicitly stated suspect information")
    witness_details: list[str] = Field(default_factory=list, description="Explicit witness observations")
    identification_details: list[str] = Field(
        default_factory=list,
        description="Explicit identifiers such as collar number, registration, serial number, colour, breed or marks",
    )
    narrative: str = Field(description="Faithful factual account preserving uncertainty and excluding inferred facts")
    requested_action: str | None = Field(default=None, description="Action explicitly requested from police")


class DraftAuthority(BaseModel):
    chunk_id: str
    title: str
    section: str | None = None
    page_start: int
    page_end: int
    excerpt: str
    reranker_score: float


class DocumentDraftRequest(BaseModel):
    doc_type: str = Field(default="fir", pattern="^fir$")
    case_description: str = Field(min_length=20, max_length=12000)


class DocumentDraftResponse(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    doc_type: str
    version: int
    status: str
    facts: FIRFacts
    missing_fields: list[str]
    authorities: list[DraftAuthority]
    rendered_text: str
    disclaimer: str
    created_at: datetime
