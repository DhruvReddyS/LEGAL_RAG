from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import CaseRoleType


CaseStatus = Literal["open", "closed", "archived"]


class CaseCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    role_type: CaseRoleType | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 3:
            raise ValueError("title must contain at least 3 non-whitespace characters")
        return value


class CaseUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    status: CaseStatus | None = None

    @field_validator("title")
    @classmethod
    def normalize_optional_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        if len(value) < 3:
            raise ValueError("title must contain at least 3 non-whitespace characters")
        return value


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    role_type: CaseRoleType
    title: str
    status: CaseStatus
    created_at: datetime


class CaseListResponse(BaseModel):
    cases: list[CaseResponse]
    total: int
