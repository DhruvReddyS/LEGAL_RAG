from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class RetrievalFilterRequest(BaseModel):
    source_types: list[str] = Field(default_factory=list)
    courts: list[str] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=list)
    acts: list[str] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    year_from: int | None = Field(default=None, ge=1, le=9999)
    year_to: int | None = Field(default=None, ge=1, le=9999)
    date_from: date | None = None
    date_to: date | None = None
    current_only: bool = False
    corpus_tiers: list[str] = Field(default_factory=lambda: ["gold", "extended"])

    @model_validator(mode="after")
    def validate_ranges(self) -> RetrievalFilterRequest:
        if self.year_from is not None and self.year_to is not None:
            if self.year_from > self.year_to:
                raise ValueError("year_from must be less than or equal to year_to")
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("date_from must be less than or equal to date_to")
        return self


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    filters: RetrievalFilterRequest = Field(default_factory=RetrievalFilterRequest)
    candidate_limit: int = Field(default=20, ge=5, le=100)
    result_limit: int = Field(default=5, ge=1, le=20)

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value

    @model_validator(mode="after")
    def validate_limits(self) -> RetrievalRequest:
        if self.result_limit > self.candidate_limit:
            raise ValueError("result_limit must be less than or equal to candidate_limit")
        return self


class RetrievalHitResponse(BaseModel):
    point_id: str
    payload: dict[str, Any]
    dense_score: float | None
    sparse_score: float | None
    fused_score: float
    reranker_score: float


class RetrievalResponse(BaseModel):
    query: str
    results: list[RetrievalHitResponse]


class ScopedRetrievalResponse(RetrievalResponse):
    mode: str
    authorized_case_ids: list[str]


class GroundedAnswerRequest(RetrievalRequest):
    pass


class PipelineTimingsResponse(BaseModel):
    embedding_ms: float
    qdrant_ms: float
    reranking_ms: float
    generation_ms: float
    total_ms: float


class GroundedAnswerResponse(BaseModel):
    query: str
    answer: str
    sources: list[RetrievalHitResponse]
    grounded: bool
    timings: PipelineTimingsResponse
