from __future__ import annotations

import uuid
import asyncio
from datetime import datetime
from contextlib import suppress
import hashlib
from decimal import Decimal
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.orchestrator import LegalRAGWorkflow
from app.core.database import get_db_session
from app.core.config import settings
from app.core.permissions import CHAT_USE
from app.core.rbac import require_permission
from app.models import AuditLog, Case, ChatMessage, ChatSession, Job, User
from app.models.enums import ChatMessageRole, JobStatus, JobType, UserRole
from app.schemas.chat import (
    ChatQueryRequest,
    ChatQueryResponse,
    ChatSessionListResponse,
    ChatSessionResponse,
    ChatSessionSummary,
)
from app.schemas.agents import AgentTraceEvent, QueryIntent
from app.services.adaptive_routing import route_legal_query
from app.services.citizen_safety import screen_citizen_query
from app.services.rate_limit import RateLimitExceeded, user_rate_limiter
from app.services.jobs import append_job_event


router = APIRouter(prefix="/chat", tags=["chat"])


async def run_while_connected(http_request: Request, coroutine):
    """Cancel synchronous research when its browser request is stopped/disconnected."""
    task = asyncio.create_task(coroutine)
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.25)
            if not task.done() and await http_request.is_disconnected():
                raise HTTPException(499, "Research stopped by client")
        return await task
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


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
        history: list[dict[str, str]] = [message.model_dump() for message in request.prior_messages]
        for message in request.prior_messages:
            session.add(ChatMessage(session_id=chat_session.id, role=ChatMessageRole(message.role), content=message.content, citations=[]))
    else:
        if request.prior_messages:
            raise HTTPException(409, "Edited conversations must start a new session")
        chat_session = await _owned_session(session, request.session_id, user)
        if request.case_id is not None and request.case_id != chat_session.case_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="case_id does not match the existing chat session")
        history = [{"role": message.role.value, "content": message.content} for message in chat_session.messages[-8:]]

    user_message = ChatMessage(
        session_id=chat_session.id,
        role=ChatMessageRole.USER,
        content=request.query,
        citations=[],
    )
    session.add(user_message)
    await session.flush()
    # Screened before routing, retrieval or generation. An emergency needs a
    # phone number now, and a request for a decision or an outcome would
    # otherwise be answered fluently from statute text and pass verification,
    # because every claim would be grounded. Grounding is not appropriateness.
    intervention = screen_citizen_query(request.query)
    if intervention is not None:
        assistant_message = ChatMessage(
            session_id=chat_session.id,
            role=ChatMessageRole.ASSISTANT,
            content=intervention.answer,
            citations=[],
            confidence_score=Decimal("0"),
        )
        session.add(assistant_message)
        await session.flush()
        session.add(
            AuditLog(
                user_id=user.id,
                action=f"chat.{intervention.kind}",
                resource_type="chat_session",
                resource_id=chat_session.id,
                metadata_={
                    "message_id": str(assistant_message.id),
                    "reason": intervention.reason,
                    # The query itself is deliberately not recorded here: an
                    # audit row must not become the durable copy of a distress
                    # disclosure. The session already holds the user message.
                },
            )
        )
        await session.commit()
        timings = {"api_total_ms": round((perf_counter() - request_started) * 1000, 2)}
        return ChatQueryResponse(
            session_id=chat_session.id,
            message_id=assistant_message.id,
            answer=intervention.answer,
            citations=[],
            confidence_score=0.0,
            evidence_strength="insufficient",
            intent=QueryIntent(
                intent=intervention.kind,
                entities=[],
                language="English",
                complexity="simple",
                retrieval_query="",
            ),
            agent_trace=[
                AgentTraceEvent(
                    node="citizen_safety",
                    details={"kind": intervention.kind, "reason": intervention.reason},
                )
            ],
            response_mode="fast",
            requested_mode=request.response_mode,
            routing_reason=f"safety_{intervention.kind}",
            routing_signals=[intervention.reason],
            timings_ms=timings,
            pipeline_metrics=[],
            latency_target_ms=settings.fast_latency_target_ms,
            target_met=True,
        )

    from app.services.citizen_context import select_document_context
    document_context = select_document_context(request.query, request.documents)
    routing = route_legal_query(
        query=request.query,
        requested_mode="deep" if document_context else request.response_mode,
        case_id=chat_session.case_id,
    )
    if routing.selected_mode == "deep" and not settings.legacy_sync_long_running_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Synchronous Deep Review is disabled; enqueue /jobs/deep-review",
        )
    try:
        await user_rate_limiter.admit(
            str(user.id),
            "chat_fast" if routing.selected_mode == "fast" else "chat_sync_deep",
            limit=(
                settings.fast_requests_per_minute
                if routing.selected_mode == "fast"
                else settings.sync_deep_requests_per_minute
            ),
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Per-user request limit reached",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    runner = http_request.app.state.fast_research_service if routing.selected_mode == "fast" else workflow
    result = await run_while_connected(http_request, runner.run(
        query=request.query,
        role=user.role.value,
        case_id=str(chat_session.case_id) if chat_session.case_id else None,
        history=history,
        **({"document_context": document_context} if document_context else {}),
    ))
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
    if (
        routing.selected_mode == "fast"
        and result["confidence_score"] < settings.fast_auto_escalation_threshold
    ):
        try:
            await user_rate_limiter.admit(
                str(user.id),
                "job_enqueue",
                limit=settings.job_enqueues_per_minute,
            )
        except RateLimitExceeded as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Per-user job enqueue limit reached",
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc
        fingerprint = hashlib.sha256(
            f"{user.id}:{user_message.id}:{request.query}".encode("utf-8")
        ).hexdigest()
        job = Job(
            user_id=user.id,
            type=JobType.DEEP_REVIEW,
            status=JobStatus.QUEUED,
            progress=0,
            idempotency_key=f"auto:{user_message.id}",
            payload={
                "request_fingerprint": fingerprint,
                "query": request.query,
                "role": user.role.value,
                "chat_session_id": str(chat_session.id),
                "case_id": str(chat_session.case_id) if chat_session.case_id else None,
                "history": history,
                "user_message_id": str(user_message.id),
                "auto_escalated_from_fast": True,
                "fast_confidence_score": result["confidence_score"],
                "fast_escalation_threshold": settings.fast_auto_escalation_threshold,
            },
            max_attempts=3,
        )
        session.add(job)
        await session.flush()
        append_job_event(
            session,
            job,
            event_type="status",
            stage="searching_more_thoroughly",
            data={
                "status": JobStatus.QUEUED.value,
                "fast_confidence_score": result["confidence_score"],
                "threshold": settings.fast_auto_escalation_threshold,
            },
        )
        trace = [event.model_dump(mode="json") for event in result["agent_trace"]]
        session.add(
            AuditLog(
                user_id=user.id,
                action="chat.auto_escalated",
                resource_type="job",
                resource_id=job.id,
                metadata_={
                    "chat_session_id": str(chat_session.id),
                    "fast_confidence_score": result["confidence_score"],
                    "threshold": settings.fast_auto_escalation_threshold,
                    "fast_citation_count": len(result["citations"]),
                    "agent_trace": trace,
                },
            )
        )
        await session.commit()
        timings = dict(result.get("timings", {}))
        timings["api_total_ms"] = round((perf_counter() - request_started) * 1000, 2)
        # The Fast brief is already computed and costs ~70ms. Discarding it
        # left the citizen staring at a blank multi-minute wait having been
        # given nothing, when provisional evidence was sitting in memory.
        # It is returned labelled as provisional and unverified; the Deep
        # answer replaces it when the job completes.
        return ChatQueryResponse(
            session_id=chat_session.id,
            answer=(
                "Checking this more thoroughly, because the quick source match "
                "was not strong enough to answer from.\n\n"
                "In the meantime, here is what the quick search found. These "
                "passages have not been verified against your question yet.\n\n"
                + result["final_answer"]
                if result["citations"]
                else "Checking this more thoroughly, because the quick search did "
                "not find a close enough match to answer from."
            ),
            citations=result["citations"],
            confidence_score=result["confidence_score"],
            evidence_strength="insufficient",
            intent=result["intent"],
            agent_trace=result["agent_trace"],
            response_mode="deep",
            requested_mode=routing.requested_mode,
            routing_reason="fast_confidence_below_escalation_threshold",
            routing_signals=[*routing.signals, "auto_escalated_low_fast_confidence"],
            timings_ms=timings,
            pipeline_metrics=result.get("stage_metrics", []),
            latency_target_ms=settings.deep_latency_target_ms,
            target_met=None,
            delivery_state="searching_more_thoroughly",
            job_id=job.id,
            escalation_threshold=settings.fast_auto_escalation_threshold,
        )
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
                "pipeline_metrics": result.get("stage_metrics", []),
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
        pipeline_metrics=result.get("stage_metrics", []),
        latency_target_ms=latency_target_ms,
        target_met=target_met,
    )


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_chat_sessions(
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: Annotated[str | None, Query(max_length=64)] = None,
    user: User = Depends(require_permission(CHAT_USE)),
    session: AsyncSession = Depends(get_db_session),
) -> ChatSessionListResponse:
    """List the caller's own conversations, most recently active first.

    Sessions and messages were already persisted, but nothing could read them
    back as a list, so the interface kept its history in sessionStorage and
    lost it when the tab closed. Rows never leave the owner: admin is not
    special-cased here, because a sidebar listing every user's conversations
    is not something any screen needs.
    """
    last_activity = func.coalesce(
        func.max(ChatMessage.created_at), ChatSession.created_at
    ).label("last_activity")
    query = (
        select(
            ChatSession,
            last_activity,
            func.count(ChatMessage.id).label("message_count"),
        )
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.user_id == user.id)
        .group_by(ChatSession.id)
        .order_by(last_activity.desc(), ChatSession.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        try:
            cursor_at = datetime.fromisoformat(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="cursor must be an ISO-8601 timestamp",
            ) from exc
        query = query.having(last_activity < cursor_at)

    rows = (await session.execute(query)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    previews: dict[uuid.UUID, str] = {}
    if rows:
        session_ids = [row[0].id for row in rows]
        newest = (
            select(
                ChatMessage.session_id,
                ChatMessage.content,
                func.row_number()
                .over(
                    partition_by=ChatMessage.session_id,
                    # Messages written in one transaction share a server-side
                    # timestamp, so created_at alone leaves the winner to the
                    # planner. An assistant message always follows the question
                    # it answers, so it wins a tie. The preference is spelled
                    # out rather than relying on the role column's sort: a
                    # PostgreSQL enum orders by declaration order, not
                    # alphabetically, so "user" sorts before "assistant".
                    order_by=(
                        ChatMessage.created_at.desc(),
                        case(
                            (ChatMessage.role == ChatMessageRole.ASSISTANT, 0),
                            else_=1,
                        ).asc(),
                    ),
                )
                .label("rank"),
            )
            .where(ChatMessage.session_id.in_(session_ids))
            .subquery()
        )
        for session_id, content in (
            await session.execute(
                select(newest.c.session_id, newest.c.content).where(newest.c.rank == 1)
            )
        ).all():
            previews[session_id] = " ".join(str(content).split())[:160]

    return ChatSessionListResponse(
        items=[
            ChatSessionSummary(
                id=chat_session.id,
                title=chat_session.title,
                case_id=chat_session.case_id,
                created_at=chat_session.created_at,
                updated_at=activity,
                message_count=message_count,
                last_message_preview=previews.get(chat_session.id),
            )
            for chat_session, activity, message_count in rows
        ],
        next_cursor=rows[-1][1].isoformat() if has_more and rows else None,
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
