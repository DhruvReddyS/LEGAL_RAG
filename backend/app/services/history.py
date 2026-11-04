"""Finding and organising a person's own conversations.

Every statement here filters on the owner, including for an administrator:
this is a person's own history, not an oversight tool.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChatMessage, ChatSession, ChatSessionMeta, User

MAX_PINNED = 5
SNIPPET_RADIUS = 70


def escape_like(term: str) -> str:
    """So a question about "100% refund" is not a wildcard pattern."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def snippet_around(text: str, term: str) -> str:
    """A short window of the text around the first match, case-insensitively."""
    flat = " ".join(text.split())
    index = flat.casefold().find(term.casefold())
    if index < 0:
        return flat[: SNIPPET_RADIUS * 2]
    start = max(0, index - SNIPPET_RADIUS)
    end = min(len(flat), index + len(term) + SNIPPET_RADIUS)
    return ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")


def encode_cursor(activity: datetime, session_id: uuid.UUID) -> str:
    return f"{activity.isoformat()}|{session_id}"


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Time and id together, because messages written in one transaction tie."""
    try:
        at, _, raw_id = cursor.partition("|")
        return datetime.fromisoformat(at), uuid.UUID(raw_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid cursor"
        ) from exc


def _activity_subquery(user_id: uuid.UUID):
    return (
        select(
            ChatSession.id.label("session_id"),
            func.coalesce(func.max(ChatMessage.created_at), ChatSession.created_at).label("activity"),
            func.count(ChatMessage.id).label("message_count"),
        )
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.user_id == user_id)
        .group_by(ChatSession.id)
        .subquery()
    )


async def list_sessions(
    session: AsyncSession,
    user: User,
    *,
    limit: int,
    cursor: str | None = None,
    pinned: bool | None = None,
    matter: str | None = None,
    case_id: uuid.UUID | None = None,
    term: str | None = None,
) -> tuple[list[dict], str | None]:
    activity = _activity_subquery(user.id)
    query = (
        select(ChatSession, activity.c.activity, activity.c.message_count, ChatSessionMeta)
        .join(activity, activity.c.session_id == ChatSession.id)
        .outerjoin(ChatSessionMeta, ChatSessionMeta.session_id == ChatSession.id)
        .where(ChatSession.user_id == user.id)
    )
    if pinned is True:
        query = query.where(ChatSessionMeta.pinned_at.is_not(None))
    elif pinned is False:
        query = query.where(ChatSessionMeta.pinned_at.is_(None))
    if matter is not None:
        query = query.where(ChatSessionMeta.matter == matter)
    if case_id is not None:
        query = query.where(ChatSession.case_id == case_id)
    pattern: str | None = None
    if term:
        pattern = f"%{escape_like(term)}%"
        matching_message = (
            select(ChatMessage.id)
            .where(
                ChatMessage.session_id == ChatSession.id,
                ChatMessage.content.ilike(pattern, escape="\\"),
            )
            .exists()
        )
        query = query.where(
            or_(
                ChatSession.title.ilike(pattern, escape="\\"),
                ChatSessionMeta.matter.ilike(pattern, escape="\\"),
                matching_message,
            )
        )
    if cursor:
        at, last_id = decode_cursor(cursor)
        query = query.where(
            or_(
                activity.c.activity < at,
                and_(activity.c.activity == at, ChatSession.id < last_id),
            )
        )
    rows = (
        await session.execute(
            query.order_by(activity.c.activity.desc(), ChatSession.id.desc()).limit(limit + 1)
        )
    ).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    session_ids = [row[0].id for row in rows]
    previews: dict[uuid.UUID, str] = {}
    if session_ids:
        ranked = (
            select(
                ChatMessage.session_id,
                ChatMessage.content,
                func.row_number()
                .over(partition_by=ChatMessage.session_id, order_by=ChatMessage.sequence.desc())
                .label("rank"),
            )
            .where(ChatMessage.session_id.in_(session_ids))
            .subquery()
        )
        for session_id, content in (
            await session.execute(select(ranked.c.session_id, ranked.c.content).where(ranked.c.rank == 1))
        ).all():
            previews[session_id] = " ".join(str(content).split())[:160]

    snippets: dict[uuid.UUID, str] = {}
    if pattern and session_ids:
        first_hit = (
            select(
                ChatMessage.session_id,
                ChatMessage.content,
                func.row_number()
                .over(partition_by=ChatMessage.session_id, order_by=ChatMessage.sequence)
                .label("rank"),
            )
            .where(
                ChatMessage.session_id.in_(session_ids),
                ChatMessage.content.ilike(pattern, escape="\\"),
            )
            .subquery()
        )
        for session_id, content in (
            await session.execute(
                select(first_hit.c.session_id, first_hit.c.content).where(first_hit.c.rank == 1)
            )
        ).all():
            snippets[session_id] = snippet_around(str(content), term or "")

    items = [
        {
            "id": chat.id,
            "title": chat.title,
            "case_id": chat.case_id,
            "created_at": chat.created_at,
            "updated_at": at,
            "message_count": count,
            "last_message_preview": previews.get(chat.id),
            "pinned": bool(meta and meta.pinned_at),
            "matter": meta.matter if meta else None,
            "match_snippet": snippets.get(chat.id),
        }
        for chat, at, count, meta in rows
    ]
    next_cursor = encode_cursor(rows[-1][1], rows[-1][0].id) if has_more and rows else None
    return items, next_cursor


async def _owned(session: AsyncSession, session_id: uuid.UUID, user: User) -> ChatSession:
    chat = await session.get(ChatSession, session_id)
    # 404 for both: whether someone else's conversation exists is not an answer
    # this route gives.
    if chat is None or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return chat


async def _upsert_meta(
    session: AsyncSession, session_id: uuid.UUID, user: User, **values: object
) -> None:
    await session.execute(
        insert(ChatSessionMeta)
        .values(session_id=session_id, user_id=user.id, **values)
        .on_conflict_do_update(index_elements=["session_id"], set_=values)
    )


async def set_pinned(session: AsyncSession, session_id: uuid.UUID, user: User, pinned: bool) -> None:
    await _owned(session, session_id, user)
    if pinned:
        count = int(
            await session.scalar(
                select(func.count())
                .select_from(ChatSessionMeta)
                .where(
                    ChatSessionMeta.user_id == user.id,
                    ChatSessionMeta.pinned_at.is_not(None),
                    ChatSessionMeta.session_id != session_id,
                )
            )
            or 0
        )
        if count >= MAX_PINNED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"You can pin up to {MAX_PINNED} conversations. Unpin one first.",
            )
    await _upsert_meta(
        session,
        session_id,
        user,
        pinned_at=datetime.now(timezone.utc) if pinned else None,
    )


async def set_matter(
    session: AsyncSession, session_id: uuid.UUID, user: User, matter: str | None
) -> None:
    await _owned(session, session_id, user)
    await _upsert_meta(session, session_id, user, matter=matter)


async def list_matters(session: AsyncSession, user: User) -> list[dict]:
    rows = await session.execute(
        select(ChatSessionMeta.matter, func.count())
        .where(ChatSessionMeta.user_id == user.id, ChatSessionMeta.matter.is_not(None))
        .group_by(ChatSessionMeta.matter)
        .order_by(ChatSessionMeta.matter)
    )
    return [{"matter": matter, "count": count} for matter, count in rows.all()]
