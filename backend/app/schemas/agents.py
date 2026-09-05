from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryIntent(BaseModel):
    intent: str = "legal_research"
    entities: list[str] = Field(default_factory=list)
    language: str = "English"
    complexity: Literal["simple", "complex"] = "simple"
    retrieval_query: str


class ClaimVerification(BaseModel):
    claim: str
    chunk_id: str
    category: Literal[
        "direct_answer", "legal_basis", "application", "next_step", "limit"
    ] = "legal_basis"
    verdict: Literal["yes", "partial", "no"]
    reason: str = ""


class VerificationResult(BaseModel):
    score: float = Field(ge=0, le=1)
    supported_claims: int = 0
    total_claims: int = 0
    claims: list[ClaimVerification] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)


class SectionMappingRef(BaseModel):
    """Where a cited provision moved to.

    `ingredients_changed` is the field that matters: some pairs are pure
    renumberings and some are new offences occupying the old one's place.
    Presenting the second kind as equivalence gets the elements wrong.
    """

    from_code: str
    from_section: str
    to_code: str
    to_section: str
    subject: str = ""
    ingredients_changed: bool = False
    note: str = ""


class AgentCitation(BaseModel):
    number: int
    chunk_id: str
    title: str
    source_type: str
    page_start: int
    page_end: int
    court: str | None = None
    act_name: str | None = None
    section: str | None = None
    source_url: str | None = None
    excerpt: str
    retrieval_score: float | None = None
    verification_status: Literal["verified", "partial", "unverified"] = "unverified"
    current_status: Literal[
        "current", "superseded", "repealed", "status_unverified", "not_applicable"
    ] = "status_unverified"
    # Named when the Act was repealed: 21% of the corpus is the IPC, CrPC and
    # Evidence Act, replaced on 1 July 2024. They still govern conduct before
    # that date, so they are cited rather than withheld -- but never silently.
    replaced_by: str | None = None
    repealed_on: str | None = None
    # Two different warnings, deliberately not merged. "no_longer_in_force"
    # attaches to the repealed Act itself; "concerns_repealed_provision"
    # attaches to guidance, manuals and judgments *about* a provision that has
    # moved -- documents which are themselves still operative, and which it
    # would be false to mark as out of force.
    repeal_label: Literal[
        "none", "no_longer_in_force", "concerns_repealed_provision"
    ] = "none"
    section_mappings: list[SectionMappingRef] = Field(default_factory=list)
    unmapped_repealed_provisions: list[str] = Field(default_factory=list)
    mapping_review_status: str | None = None


class AgentTraceEvent(BaseModel):
    node: str
    details: dict[str, Any] = Field(default_factory=dict)
