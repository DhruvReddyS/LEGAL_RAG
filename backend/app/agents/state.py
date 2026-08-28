from __future__ import annotations

from typing import Any, TypedDict

from app.schemas.agents import AgentCitation, AgentTraceEvent, QueryIntent, VerificationResult
from app.services.retrieval import RetrievalHit


class AgentState(TypedDict, total=False):
    query: str
    role: str
    case_id: str | None
    specialist_agent_id: str
    specialist_agent_label: str
    specialist_agent_objective: str
    history: list[dict[str, str]]
    intent: QueryIntent
    retrieval_query: str
    retrieved_chunks: list[RetrievalHit]
    draft_answer: str
    verification_result: VerificationResult
    final_answer: str
    citations: list[AgentCitation]
    confidence_score: float
    evidence_strength: str
    retry_count: int
    agent_trace: list[AgentTraceEvent]
    timings: dict[str, Any]
