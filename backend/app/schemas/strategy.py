from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.agents import AgentCitation


class StrategyPoint(BaseModel):
    category: Literal[
        "prosecution_theory",
        "disputed_element",
        "evidentiary_gap",
        "procedural_issue",
        "defence_point",
        "likely_counterargument",
        "further_fact_needed",
    ]
    point: str = Field(min_length=5, max_length=1200)
    source_chunk_ids: list[str] = Field(default_factory=list)


class DefenceAnalysisDraft(BaseModel):
    summary: str = Field(min_length=5, max_length=2000)
    points: list[StrategyPoint] = Field(default_factory=list, max_length=20)


class DefenceAnalysisRequest(BaseModel):
    case_scenario: str = Field(min_length=40, max_length=12000)
    advocate_position: str | None = Field(default=None, max_length=4000)


class VerifiedStrategyPoint(StrategyPoint):
    verification: Literal["yes", "partial"]
    verification_reason: str = ""


class DefenceAnalysisResponse(BaseModel):
    summary: str
    points: list[VerifiedStrategyPoint]
    citations: list[AgentCitation]
    confidence_score: float = Field(ge=0, le=1)
    evidence_strength: Literal["strong", "moderate", "insufficient"]
    rejected_point_count: int
    disclaimer: str
