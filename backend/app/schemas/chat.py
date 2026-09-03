from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# C0 and C1 control characters, keeping none of them: a legal question has
# no use for a vertical tab, and NUL cannot be stored at all.
_CONTROL_CHARACTERS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

from app.schemas.agents import AgentCitation, AgentTraceEvent, QueryIntent


class CitizenDocumentPage(BaseModel):
    page: int = Field(ge=1, le=20)
    text: str = Field(max_length=12000)


class CitizenDocumentContext(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    pages: list[CitizenDocumentPage] = Field(min_length=1, max_length=20)


class PriorChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    session_id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None
    response_mode: Literal["auto", "fast", "deep"] = "deep"
    documents: list[CitizenDocumentContext] = Field(default_factory=list, max_length=3)
    prior_messages: list[PriorChatMessage] = Field(default_factory=list, max_length=8)

    @field_validator("documents")
    @classmethod
    def bound_document_text(cls, documents: list[CitizenDocumentContext]) -> list[CitizenDocumentContext]:
        if sum(len(page.text) for doc in documents for page in doc.pages) > 36000:
            raise ValueError("Combined document text exceeds 36,000 characters")
        return documents

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        # Control characters arrive routinely from a PDF copy-paste. PostgreSQL
        # text columns cannot hold a NUL byte at all, so one reaching the
        # message insert failed the request with a 500 after the pipeline had
        # already run.
        value = _CONTROL_CHARACTERS_RE.sub(" ", value)
        value = " ".join(value.split())
        if not value:
            raise ValueError("query must not be blank")
        # Retrieval needs something to search for. A query of only punctuation
        # produced no search terms and crashed on an empty term set.
        if not any(character.isalnum() for character in value):
            raise ValueError("query must contain letters or numbers")
        return value


class ChatQueryResponse(BaseModel):
    session_id: uuid.UUID
    message_id: uuid.UUID | None = None
    answer: str
    citations: list[AgentCitation]
    confidence_score: float
    evidence_strength: str
    intent: QueryIntent
    agent_trace: list[AgentTraceEvent]
    response_mode: Literal["fast", "deep"]
    requested_mode: Literal["auto", "fast", "deep"]
    routing_reason: str
    routing_signals: list[str]
    timings_ms: dict[str, Any]
    pipeline_metrics: list[dict[str, Any]] = Field(default_factory=list)
    latency_target_ms: int
    target_met: bool | None
    delivery_state: Literal["complete", "searching_more_thoroughly"] = "complete"
    job_id: uuid.UUID | None = None
    escalation_threshold: float | None = None


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list[dict]
    confidence_score: float | None
    created_at: datetime


class ChatSessionSummary(BaseModel):
    """A sidebar row. Deliberately excludes message bodies.

    Listing sessions must not ship every message of every conversation, which
    for a case-scoped session can include private evidence excerpts.
    """

    id: uuid.UUID
    title: str
    case_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_message_preview: str | None = None


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionSummary]
    next_cursor: str | None = None


class ChatSessionResponse(BaseModel):
    id: uuid.UUID
    title: str
    case_id: uuid.UUID | None
    created_at: datetime
    messages: list[ChatMessageResponse]
