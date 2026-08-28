from __future__ import annotations

import uuid
from decimal import Decimal
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.orchestrator import LegalRAGWorkflow
from app.core.database import get_db_session
from app.core.config import settings
from app.core.permissions import CHAT_USE
from app.core.rbac import require_permission
from app.models import AuditLog, Case, ChatMessage, ChatSession, User
from app.models.enums import ChatMessageRole, UserRole
from app.schemas.chat import ChatQueryRequest, ChatQueryResponse, ChatSessionResponse
from app.schemas.agents import AgentTraceEvent
from app.services.adaptive_routing import route_legal_query


router = APIRouter(prefix="/chat", tags=["chat"])


def get_workflow(request: Request) -> LegalRAGWorkflow:
    return request.app.state.legal_rag_workflow


async def _owned_session(session: AsyncSession, session_id: uuid.UUID, user: User) -> ChatSession:
    chat_session = await session.scalar(
        select(ChatSession).options(selectinload(ChatSession.messages)).where(ChatSession.id == session_id)
    )
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if chat_session.user_id != user.id and user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You do not own this chat session")
    return chat_session


async def _validate_case(session: AsyncSession, case_id: uuid.UUID, user: User) -> None:
    case = await session.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.owner_id != user.id and user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You do not own this case")
    if user.role in {UserRole.POLICE, UserRole.ADVOCATE} and case.role_type.value != user.role.value:
        raise HTTPException(status_code=403, detail="Case role does not match the current user role")


@router.post("/query", response_model=ChatQueryResponse)
async def query_chat(
    request: ChatQueryRequest,
    http_request: Request,
    workflow: Annotated[LegalRAGWorkflow, Depends(get_workflow)],
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> ChatQueryResponse:
    request_started = perf_counter()
    if request.session_id is None:
        if request.case_id is not None:
            await _validate_case(session, request.case_id, user)
        chat_session = ChatSession(user_id=user.id, case_id=request.case_id, title=request.query[:120])
        session.add(chat_session)
        await session.flush()
        history: list[dict[str, str]] = []
    else:
        chat_session = await _owned_session(session, request.session_id, user)
        if request.case_id is not None and request.case_id != chat_session.case_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="case_id does not match the existing chat session")
        history = [{"role": message.role.value, "content": message.content} for message in chat_session.messages[-8:]]

    session.add(ChatMessage(session_id=chat_session.id, role=ChatMessageRole.USER, content=request.query, citations=[]))
    routing = route_legal_query(
        query=request.query,
        requested_mode=request.response_mode,
        case_id=chat_session.case_id,
    )
    runner = http_request.app.state.fast_research_service if routing.selected_mode == "fast" else workflow
    result = await runner.run(
        query=request.query,
        role=user.role.value,
        case_id=str(chat_session.case_id) if chat_session.case_id else None,
        history=history,
    )
    result["agent_trace"] = [
        *result["agent_trace"],
        AgentTraceEvent(
            node="adaptive_router",
            details={
                "requested_mode": routing.requested_mode,
                "selected_mode": routing.selected_mode,
                "reason": routing.reason,
                "signals": list(routing.signals),
            },
        ),
    ]
    citations = [citation.model_dump(mode="json") for citation in result["citations"]]
    assistant_message = ChatMessage(
        session_id=chat_session.id,
        role=ChatMessageRole.ASSISTANT,
        content=result["final_answer"],
        citations=citations,
        confidence_score=Decimal(str(round(result["confidence_score"], 4))),
    )
    session.add(assistant_message)
    await session.flush()
    trace = [event.model_dump(mode="json") for event in result["agent_trace"]]
    session.add(
        AuditLog(
            user_id=user.id,
            action="chat.query",
            resource_type="chat_session",
            resource_id=chat_session.id,
            metadata_={
                "message_id": str(assistant_message.id),
                "case_id": str(chat_session.case_id) if chat_session.case_id else None,
                "confidence_score": result["confidence_score"],
                "evidence_strength": result["evidence_strength"],
                "requested_mode": routing.requested_mode,
                "response_mode": routing.selected_mode,
                "routing_reason": routing.reason,
                "routing_signals": list(routing.signals),
                "timings_ms": result.get("timings", {}),
                "agent_trace": trace,
            },
        )
    )
    await session.commit()
    timings = dict(result.get("timings", {}))
    timings["api_total_ms"] = round((perf_counter() - request_started) * 1000, 2)
    latency_target_ms = settings.fast_latency_target_ms if routing.selected_mode == "fast" else settings.deep_latency_target_ms
    target_met = timings["api_total_ms"] <= latency_target_ms if routing.selected_mode == "fast" else None
    return ChatQueryResponse(
        session_id=chat_session.id,
        message_id=assistant_message.id,
        answer=result["final_answer"],
        citations=result["citations"],
        confidence_score=result["confidence_score"],
        evidence_strength=result["evidence_strength"],
        intent=result["intent"],
        agent_trace=result["agent_trace"],
        response_mode=routing.selected_mode,
        requested_mode=routing.requested_mode,
        routing_reason=routing.reason,
        routing_signals=list(routing.signals),
        timings_ms=timings,
        latency_target_ms=latency_target_ms,
        target_met=target_met,
    )


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def read_chat_session(
    session_id: uuid.UUID,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> ChatSessionResponse:
    chat_session = await _owned_session(session, session_id, user)
    return ChatSessionResponse(
        id=chat_session.id,
        title=chat_session.title,
        case_id=chat_session.case_id,
        created_at=chat_session.created_at,
        messages=[
            {
                "id": message.id,
                "role": message.role.value,
                "content": message.content,
                "citations": message.citations,
                "confidence_score": float(message.confidence_score) if message.confidence_score is not None else None,
                "created_at": message.created_at,
            }
            for message in chat_session.messages
        ],
    )
