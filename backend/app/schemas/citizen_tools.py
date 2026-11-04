from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_CONTROL_CHARACTERS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _clean(value: str) -> str:
    return _CONTROL_CHARACTERS_RE.sub(" ", value).strip()


Language = Literal["en", "hi", "te"]
LocalisedText = dict[str, str]
DeadlineStatus = Literal["done", "overdue", "due_today", "due_soon", "upcoming"]


class NoticeExplainRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    plain_language: bool = False
    language: Language = "en"

    @field_validator("text")
    @classmethod
    def normalise(cls, value: str) -> str:
        value = _clean(value)
        if not any(character.isalnum() for character in value):
            raise ValueError("Paste the text of the notice")
        return value


class NoticeProvision(BaseModel):
    id: str
    label: str
    act_name: str
    quote: str
    page: int | None
    source_url: str | None


class NoticeDate(BaseModel):
    raw: str
    iso: str | None
    context: str


class NoticeDeadline(BaseModel):
    days: int
    quote: str


class CitedProvision(BaseModel):
    raw: str
    code: str | None
    section: str
    status: Literal["replaced", "in_force_code", "not_checked"]
    replaced_on: str | None = None
    successors: list[str] = Field(default_factory=list)
    no_successor: bool = False
    ingredients_changed: bool = False


class PlainDemand(BaseModel):
    plain: str
    quote: str


class PlainSummary(BaseModel):
    summary: str
    demands: list[PlainDemand] = Field(default_factory=list)
    language: Language


class NoticeExplainResponse(BaseModel):
    notice_type: str
    type_label: LocalisedText
    abstained: bool
    what_this_is: LocalisedText
    risk: LocalisedText
    statutory_deadline: LocalisedText | None
    provisions: list[NoticeProvision]
    demands: list[str]
    deadlines: list[NoticeDeadline]
    dates: list[NoticeDate]
    amounts: list[str]
    cited_provisions: list[CitedProvision]
    flags: list[LocalisedText]
    plain: PlainSummary | None
    plain_status: Literal["not_requested", "ok", "unavailable", "rejected"]
    disclaimer: LocalisedText


class DeadlineCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_on: date
    remind_days_before: int = Field(default=7, ge=0, le=90)
    notes: str | None = Field(default=None, max_length=2000)
    source: Literal["manual", "notice", "router"] = "manual"
    provision_label: str | None = Field(default=None, max_length=160)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = _clean(value)
        if not value:
            raise ValueError("Give this date a name")
        return value

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        return (_clean(value) or None) if value is not None else None


class DeadlineUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_on: date | None = None
    remind_days_before: int | None = Field(default=None, ge=0, le=90)
    notes: str | None = Field(default=None, max_length=2000)
    completed: bool | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _clean(value)
        if not value:
            raise ValueError("Give this date a name")
        return value


class DeadlineResponse(BaseModel):
    id: uuid.UUID
    title: str
    due_on: date
    remind_days_before: int
    notes: str | None
    source: str
    provision_label: str | None
    completed_at: datetime | None
    created_at: datetime
    status: DeadlineStatus
    days_left: int


class DeadlineListResponse(BaseModel):
    items: list[DeadlineResponse]
    today: date
