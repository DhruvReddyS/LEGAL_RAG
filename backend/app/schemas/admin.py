from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator

from app.models.enums import CorpusSourceType, UserRole


ProfessionalRole = Literal[UserRole.POLICE, UserRole.ADVOCATE]


class AdminUserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)
    role: ProfessionalRole


class AdminUserUpdate(BaseModel):
    role: ProfessionalRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> "AdminUserUpdate":
        if self.role is None and self.is_active is None:
            raise ValueError("At least one account change is required")
        return self


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime
    case_count: int = 0


class AdminUserListResponse(BaseModel):
    users: list[AdminUserResponse]
    total: int


class CorpusIntakeResponse(BaseModel):
    id: uuid.UUID
    storage_object_id: uuid.UUID
    corpus_source_id: uuid.UUID | None
    title: str
    source_type: CorpusSourceType
    jurisdiction: str
    authority: str | None
    source_url: str
    status: str
    filename: str
    file_size: int
    sha256: str
    validation_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CorpusIntakeListResponse(BaseModel):
    intakes: list[CorpusIntakeResponse]
    total: int


class CorpusPublishResponse(BaseModel):
    intake: CorpusIntakeResponse
    indexed_chunks: int
    corpus_tier: Literal["extended"] = "extended"


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    actor_name: str | None
    action: str
    resource_type: str
    resource_id: uuid.UUID | None
    metadata: dict[str, Any]
    timestamp: datetime


class AuditEventListResponse(BaseModel):
    events: list[AuditEventResponse]
    total: int


class AdminOverviewResponse(BaseModel):
    users_total: int
    police_active: int
    advocates_active: int
    staged_intakes: int
    validated_intakes: int
    published_intakes: int
    audit_events: int
