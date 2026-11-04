"""Feedback triage and corpus incidents.

A bad answer is traced to the corpus passages it cited, and a document can be
withheld from retrieval the moment it is found to be wrong.

The boundary: a conversation attached to a case contains private matter material,
and a thumbs-down is not an authorised matter. For those the trace shows only
what is proved to come from the global corpus. The answer, the correction and any
citation not found there are withheld. Fail closed: if the corpus cannot be
reached, nothing from a case-linked answer is shown.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from qdrant_client import models
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.models import AuditLog, ChatMessage, ChatSession, Feedback, User
from app.models.admin_tools import DocumentQuarantine, FeedbackTriage
from app.models.enums import FeedbackRating
from app.services import quarantine
from app.services.admin_corpus import manifest_document

_PUBLIC_CITATION_FIELDS = (
    "number",
    "chunk_id",
    "title",
    "source_type",
    "page_start",
    "page_end",
    "court",
    "act_name",
    "section",
    "source_url",
    "excerpt",
    "retrieval_score",
    "verification_status",
    "current_status",
    "replaced_by",
)


def point_id_for_chunk(chunk_id: str) -> str:
    # The id the writer gives each point.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


async def list_feedback(
    session: AsyncSession,
    *,
    rating: str | None,
    status: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    triage_status = func.coalesce(FeedbackTriage.status, "open")
    filters = []
    if rating:
        filters.append(Feedback.rating == FeedbackRating(rating))
    if status:
        filters.append(triage_status == status)
    base = (
        select(Feedback.id)
        .join(ChatMessage, ChatMessage.id == Feedback.message_id)
        .outerjoin(FeedbackTriage, FeedbackTriage.feedback_id == Feedback.id)
        .where(*filters)
    )
    total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = (
        await session.execute(
            select(
                Feedback.id,
                Feedback.message_id,
                Feedback.rating,
                Feedback.correction_text.is_not(None),
                triage_status,
                ChatMessage.confidence_score,
                func.jsonb_array_length(ChatMessage.citations),
                ChatMessage.created_at,
                ChatSession.case_id.is_not(None),
                User.role,
            )
            .join(ChatMessage, ChatMessage.id == Feedback.message_id)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .join(User, User.id == Feedback.user_id)
            .outerjoin(FeedbackTriage, FeedbackTriage.feedback_id == Feedback.id)
            .where(*filters)
            .order_by(ChatMessage.created_at.desc(), Feedback.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": str(row[0]),
                "message_id": str(row[1]),
                "rating": row[2].value,
                "has_correction": bool(row[3]),
                "status": row[4],
                "confidence_score": float(row[5]) if row[5] is not None else None,
                "citation_count": int(row[6]),
                "answered_at": row[7].isoformat(),
                "case_linked": bool(row[8]),
                "role": row[9].value,
            }
            for row in rows
        ],
    }


async def _global_payloads(client: Any, chunk_ids: list[str]) -> dict[str, dict[str, Any]] | None:
    """Payloads of the chunks that exist in the global corpus. None when unreachable."""
    if not chunk_ids:
        return {}
    by_point = {point_id_for_chunk(chunk_id): chunk_id for chunk_id in chunk_ids}
    try:
        points = await client.retrieve(
            collection_name=GLOBAL_LEGAL_CORPUS,
            ids=list(by_point),
            with_payload=True,
            with_vectors=False,
        )
    except Exception:  # noqa: BLE001 - reported to the caller as "could not check"
        return None
    return {by_point[str(point.id)]: point.payload or {} for point in points if str(point.id) in by_point}


async def trace_feedback(
    session: AsyncSession, *, admin: User, feedback_id: uuid.UUID, client: Any
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(Feedback, ChatMessage, ChatSession)
            .join(ChatMessage, ChatMessage.id == Feedback.message_id)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(Feedback.id == feedback_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    feedback, message, chat = row
    triage = await session.get(FeedbackTriage, feedback_id)
    case_linked = chat.case_id is not None

    citations = [item for item in (message.citations or []) if isinstance(item, dict)]
    payloads = await _global_payloads(client, [str(item.get("chunk_id")) for item in citations])
    corpus_checked = payloads is not None
    shown: list[dict[str, Any]] = []
    withheld = 0
    for citation in citations:
        chunk_id = str(citation.get("chunk_id"))
        payload = (payloads or {}).get(chunk_id)
        if payload is None and case_linked:
            withheld += 1
            continue
        document_id = (payload or {}).get("canonical_document_id")
        shown.append(
            {
                **{field: citation.get(field) for field in _PUBLIC_CITATION_FIELDS},
                "canonical_document_id": document_id,
                "corpus_tier": (payload or {}).get("corpus_tier"),
                "found_in_corpus": payload is not None,
                "quarantined": bool(document_id) and quarantine.is_quarantined(document_id),
            }
        )

    # Written before the response is built: the row must exist whatever happens
    # next. It names the message and how much was shown, never what it said.
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.feedback.trace",
            resource_type="feedback",
            resource_id=feedback_id,
            metadata_={
                "message_id": str(message.id),
                "owner_id": str(chat.user_id),
                "case_linked": case_linked,
                "citations_shown": len(shown),
                "citations_withheld": withheld,
            },
        )
    )
    await session.commit()
    return {
        "id": str(feedback.id),
        "message_id": str(message.id),
        "rating": feedback.rating.value,
        "status": triage.status if triage else "open",
        "note": triage.note if triage else None,
        "confidence_score": float(message.confidence_score) if message.confidence_score is not None else None,
        "answered_at": message.created_at.isoformat(),
        "case_linked": case_linked,
        "corpus_checked": corpus_checked,
        "answer": None if case_linked else message.content,
        "correction": None if case_linked else feedback.correction_text,
        "has_correction": bool(feedback.correction_text),
        "citations": shown,
        "citations_withheld": withheld,
    }


async def update_triage(
    session: AsyncSession,
    *,
    admin: User,
    feedback_id: uuid.UUID,
    status: str,
    note: str | None,
) -> dict[str, Any]:
    if await session.get(Feedback, feedback_id) is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    triage = await session.get(FeedbackTriage, feedback_id)
    if triage is None:
        triage = FeedbackTriage(feedback_id=feedback_id)
        session.add(triage)
    triage.status = status
    triage.note = note
    triage.updated_by = admin.id
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.feedback.triage",
            resource_type="feedback",
            resource_id=feedback_id,
            metadata_={"status": status, "has_note": bool(note)},
        )
    )
    await session.commit()
    return {"id": str(feedback_id), "status": status, "note": note}


def _document_filter(canonical_document_id: str) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="canonical_document_id",
                match=models.MatchValue(value=canonical_document_id),
            )
        ]
    )


async def preview_quarantine(
    session: AsyncSession, *, canonical_document_id: str, client: Any
) -> dict[str, Any]:
    """The dry run: what withholding this document would take out of answers."""
    document = manifest_document(canonical_document_id)
    points: int | None
    tier: str | None = None
    try:
        counted = await client.count(
            collection_name=GLOBAL_LEGAL_CORPUS,
            count_filter=_document_filter(canonical_document_id),
            exact=True,
        )
        points = int(counted.count)
        if points:
            sample, _ = await client.scroll(
                collection_name=GLOBAL_LEGAL_CORPUS,
                scroll_filter=_document_filter(canonical_document_id),
                limit=1,
                with_payload=["corpus_tier", "title"],
            )
            if sample:
                tier = (sample[0].payload or {}).get("corpus_tier")
    except Exception:  # noqa: BLE001 - the preview says it could not count
        points = None
    active = await _active_quarantine(session, canonical_document_id)
    return {
        "canonical_document_id": canonical_document_id,
        "title": document.title if document else None,
        "in_manifest": document is not None,
        "current_status": document.current_status if document else None,
        "points_in_serving_collection": points,
        "corpus_tier": tier,
        "serving_collection": GLOBAL_LEGAL_CORPUS,
        "already_quarantined": active is not None,
    }


async def _active_quarantine(session: AsyncSession, canonical_document_id: str) -> DocumentQuarantine | None:
    return await session.scalar(
        select(DocumentQuarantine).where(
            DocumentQuarantine.canonical_document_id == canonical_document_id,
            DocumentQuarantine.released_at.is_(None),
        )
    )


def _quarantine_row(row: DocumentQuarantine) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "canonical_document_id": row.canonical_document_id,
        "title": row.title,
        "reason": row.reason,
        "feedback_id": str(row.feedback_id) if row.feedback_id else None,
        "quarantined_at": row.quarantined_at.isoformat() if row.quarantined_at else None,
        "released_at": row.released_at.isoformat() if row.released_at else None,
        "release_reason": row.release_reason,
    }


async def list_quarantines(session: AsyncSession, *, include_released: bool) -> list[dict[str, Any]]:
    query = select(DocumentQuarantine).order_by(DocumentQuarantine.quarantined_at.desc()).limit(200)
    if not include_released:
        query = query.where(DocumentQuarantine.released_at.is_(None))
    return [_quarantine_row(row) for row in (await session.scalars(query)).all()]


async def quarantine_document(
    session: AsyncSession,
    *,
    admin: User,
    canonical_document_id: str,
    reason: str,
    feedback_id: uuid.UUID | None,
) -> dict[str, Any]:
    if await _active_quarantine(session, canonical_document_id) is not None:
        raise HTTPException(status_code=409, detail="This document is already quarantined")
    if feedback_id is not None and await session.get(Feedback, feedback_id) is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    document = manifest_document(canonical_document_id)
    row = DocumentQuarantine(
        canonical_document_id=canonical_document_id,
        title=document.title if document else None,
        reason=reason,
        feedback_id=feedback_id,
        quarantined_by=admin.id,
    )
    session.add(row)
    await session.flush()
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.corpus.quarantine",
            resource_type="corpus_document",
            resource_id=row.id,
            metadata_={
                "canonical_document_id": canonical_document_id,
                "feedback_id": str(feedback_id) if feedback_id else None,
            },
        )
    )
    await session.commit()
    await session.refresh(row)
    # After the commit, so the exclusion never leads a record that could roll back.
    await _publish_active_set(session)
    return _quarantine_row(row)


async def release_document(
    session: AsyncSession, *, admin: User, quarantine_id: uuid.UUID, reason: str
) -> dict[str, Any]:
    row = await session.get(DocumentQuarantine, quarantine_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Quarantine not found")
    if row.released_at is not None:
        raise HTTPException(status_code=409, detail="This quarantine has already been released")
    row.released_at = datetime.now(timezone.utc)
    row.released_by = admin.id
    row.release_reason = reason
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.corpus.quarantine_release",
            resource_type="corpus_document",
            resource_id=row.id,
            metadata_={"canonical_document_id": row.canonical_document_id},
        )
    )
    await session.commit()
    await session.refresh(row)
    await _publish_active_set(session)
    return _quarantine_row(row)


async def _publish_active_set(session: AsyncSession) -> None:
    rows = await session.scalars(
        select(DocumentQuarantine.canonical_document_id).where(
            DocumentQuarantine.released_at.is_(None)
        )
    )
    quarantine.replace_active(frozenset(rows.all()))
