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
    verdict: Literal["yes", "partial", "no"]
    reason: str = ""


class VerificationResult(BaseModel):
    score: float = Field(ge=0, le=1)
    supported_claims: int = 0
    total_claims: int = 0
    claims: list[ClaimVerification] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)


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
    current_status: Literal["current", "superseded", "status_unverified", "not_applicable"] = "status_unverified"


class AgentTraceEvent(BaseModel):
    node: str
    details: dict[str, Any] = Field(default_factory=dict)
