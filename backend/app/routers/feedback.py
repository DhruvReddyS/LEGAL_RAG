"""Answer feedback capture.

The table, the enum and the `feedback:create` permission have existed since the
initial schema. Only the endpoint was missing, so the interface rendered
helpful/not-helpful buttons that set local state and sent nothing.

This is also the cheapest quality signal available for evaluation work: a
thumbs-down on an answer whose claims all verified is exactly the case a
golden set will not surface on its own.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.permissions import FEEDBACK_CREATE
from app.core.rbac import require_permission
from app.models import AuditLog, ChatMessage, ChatSession, Feedback, User
from app.models.enums import ChatMessageRole, FeedbackRating
from app.schemas.feedback import FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    request: FeedbackRequest,
    user: User = Depends(require_permission(FEEDBACK_CREATE)),
    session: AsyncSession = Depends(get_db_session),
) -> Feedback:
    """Record a rating for one assistant message the caller owns.

    Re-rating replaces the previous verdict rather than creating a second row,
    which is what the unique constraint on (message_id, user_id) expects and
    what a toggle in the interface implies.
    """
    message = await session.scalar(
        select(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatMessage.id == request.message_id)
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")

    chat_session = await session.get(ChatSession, message.session_id)
    # Ownership is checked on the session, not the message: an admin may read
    # any conversation, but rating someone else's answer as though it were
    # their own would corrupt the signal this table exists to collect.
    if chat_session is None or chat_session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.role is not ChatMessageRole.ASSISTANT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only an assistant answer can be rated",
        )

    existing = await session.scalar(
        select(Feedback).where(
            Feedback.message_id == request.message_id,
            Feedback.user_id == user.id,
        )
    )
    if existing is None:
        existing = Feedback(
            message_id=request.message_id,
            user_id=user.id,
            rating=FeedbackRating(request.rating),
            correction_text=request.correction_text,
        )
        session.add(existing)
    else:
        existing.rating = FeedbackRating(request.rating)
        existing.correction_text = request.correction_text

    await session.flush()
    session.add(
        AuditLog(
            user_id=user.id,
            action="feedback.submitted",
            resource_type="chat_message",
            resource_id=request.message_id,
            metadata_={
                "rating": existing.rating.value,
                # The correction text itself is not duplicated into the audit
                # log; it can describe a personal legal situation and already
                # has a home on the feedback row.
                "has_correction": bool(existing.correction_text),
                "confidence_score": (
                    float(message.confidence_score)
                    if message.confidence_score is not None
                    else None
                ),
                "citation_count": len(message.citations or []),
            },
        )
    )
    await session.commit()
    await session.refresh(existing)
    return existing


@router.get("/{message_id}", response_model=FeedbackResponse | None)
async def read_feedback(
    message_id: uuid.UUID,
    user: User = Depends(require_permission(FEEDBACK_CREATE)),
    session: AsyncSession = Depends(get_db_session),
) -> Feedback | None:
    """Return the caller's own rating, so the button can restore its state."""
    return await session.scalar(
        select(Feedback).where(
            Feedback.message_id == message_id,
            Feedback.user_id == user.id,
        )
    )
