from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class HistorySession(BaseModel):
    id: uuid.UUID
    title: str
    case_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_message_preview: str | None
    pinned: bool
    matter: str | None
    match_snippet: str | None = None


class HistoryPage(BaseModel):
    items: list[HistorySession]
    next_cursor: str | None


class HistorySearch(BaseModel):
    """A search term is what someone is worried about, so it goes in the body.

    In a URL it would reach the access log, the browser history and the referrer.
    """

    term: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=30, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=128)
    matter: str | None = Field(default=None, max_length=120)
    case_id: uuid.UUID | None = None

    @field_validator("term")
    @classmethod
    def tidy(cls, value: str) -> str:
        cleaned = " ".join(value.replace("\x00", " ").split())
        if not cleaned:
            raise ValueError("term must not be blank")
        return cleaned


class PinUpdate(BaseModel):
    pinned: bool


class MatterUpdate(BaseModel):
    matter: str | None = Field(default=None, max_length=120)

    @field_validator("matter")
    @classmethod
    def tidy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.replace("\x00", " ").split()) or None


class MatterCount(BaseModel):
    matter: str
    count: int


class MatterList(BaseModel):
    items: list[MatterCount]
