from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DocumentAnalyzeRequest(BaseModel):
    document_id: uuid.UUID
    focus: str | None = Field(default=None, max_length=2000)


class SourceEvidence(BaseModel):
    point_id: str
    chunk_id: str
    title: str
    source_type: str
    section: str | None = None
    page_start: int
    page_end: int
    excerpt: str
    relevance_score: float | None = None
    verification_status: Literal["verified", "partial", "unverified"]
    current_status: Literal["current", "superseded", "status_unverified", "not_applicable"]
    scope: Literal["global", "private_case"]


class DocumentFinding(BaseModel):
    text: str
    severity: Literal["information", "review", "high"] = "review"
    evidence: list[SourceEvidence]


class ApplicableSection(BaseModel):
    label: str
    rationale: str
    evidence: SourceEvidence


class DocumentAnalysisResponse(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    document_id: uuid.UUID
    version: int
    summary: str
    key_clauses: list[DocumentFinding]
    risks: list[DocumentFinding]
    applicable_sections: list[ApplicableSection]
    rejected_section_count: int
    analyzed_chunk_count: int
    total_chunk_count: int
    partial_review: bool
    disclaimer: str
    created_at: datetime


class CaseDocumentSummary(BaseModel):
    document_id: uuid.UUID
    storage_object_id: uuid.UUID | None
    filename: str
    doc_type: str
    uploaded_at: datetime
    sha256: str | None
    page_count: int
    chunk_count: int


class CaseDocumentListResponse(BaseModel):
    documents: list[CaseDocumentSummary]
    total: int


class SourceInspectorResponse(BaseModel):
    point_id: str
    chunk_id: str
    scope: Literal["global", "private_case"]
    source_title: str
    source_type: str
    act_or_judgment: str | None
    section: str | None
    page_start: int
    page_end: int
    retrieved_passage: str
    retrieval_score: float | None
    verification_status: Literal["verified", "partial", "unverified"]
    current_status: Literal["current", "superseded", "status_unverified", "not_applicable"]
    case_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    storage_object_id: uuid.UUID | None = None
    corpus_tier: str | None = None
    verified_official: bool | None = None


class _DraftFinding(BaseModel):
    text: str = Field(min_length=1, max_length=1600)
    severity: Literal["information", "review", "high"] = "review"
    source_chunk_ids: list[str] = Field(min_length=1, max_length=4)


class _DraftApplicableSection(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=1200)


class _DraftDocumentAnalysis(BaseModel):
    summary: str = Field(min_length=1, max_length=3000)
    key_clauses: list[_DraftFinding] = Field(default_factory=list, max_length=12)
    risks: list[_DraftFinding] = Field(default_factory=list, max_length=12)
    applicable_sections: list[_DraftApplicableSection] = Field(default_factory=list, max_length=8)
