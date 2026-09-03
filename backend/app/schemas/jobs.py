from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import JobStatus, JobType


class DeepReviewJobRequest(BaseModel):
    query: str = Field(min_length=3, max_length=10_000)
    session_id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None


class OcrIngestionJobRequest(BaseModel):
    case_id: uuid.UUID
    object_id: uuid.UUID
    doc_type: str = Field(min_length=2, max_length=100)


class DocumentAnalysisJobRequest(BaseModel):
    case_id: uuid.UUID
    document_id: uuid.UUID
    focus: str | None = Field(default=None, max_length=2000)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: JobType
    status: JobStatus
    progress: int
    attempt_count: int
    max_attempts: int
    cancel_requested: bool
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class JobListResponse(BaseModel):
    items: list[JobResponse]


class JobEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: uuid.UUID
    event_type: str
    stage: str | None
    progress: int
    data: dict[str, Any]
    created_at: datetime
