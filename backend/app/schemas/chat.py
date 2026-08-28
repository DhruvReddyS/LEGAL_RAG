from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.agents import AgentCitation, AgentTraceEvent, QueryIntent


class ChatQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    session_id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None
    response_mode: Literal["auto", "fast", "deep"] = "deep"

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class ChatQueryResponse(BaseModel):
    session_id: uuid.UUID
    message_id: uuid.UUID
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
    timings_ms: dict[str, float | bool]
    latency_target_ms: int
    target_met: bool | None


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: list[dict]
    confidence_score: float | None
    created_at: datetime


class ChatSessionResponse(BaseModel):
    id: uuid.UUID
    title: str
    case_id: uuid.UUID | None
    created_at: datetime
    messages: list[ChatMessageResponse]
