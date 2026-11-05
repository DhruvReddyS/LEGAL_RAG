"""CORP-06: tell people when the law a saved answer relied on has changed.

A stored citation has no document id. It holds the chunk id, which is an opaque hash
that a rebuild changes, plus the title and act name copied from the same manifest
row. So a saved answer is matched to a document by those names, case-insensitively.

Every notice is written for the user who owns the conversation, read back through
that user's id, and holds only public facts about the law: the title and the fields
of the curated currency decision. It never holds the question or the answer.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import ARRAY, Text, bindparam, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ingestion.metadata import CanonicalDocument, iter_canonical_documents, load_manifest
from app.models import AuditLog, ChatMessage, ChatSession
from app.models.corpus_lifecycle import DocumentCurrencyState, LawChangeNotice
from app.models.enums import ChatMessageRole
from app.services import currency
from app.services.admin_corpus import _currency
from app.services.currency import CurrencyDecision, CurrencyStatus

# Arbitrary but fixed: this pass's slot in PostgreSQL's advisory lock space.
SYNC_LOCK_KEY = 720_410_601
SUPERSEDED = CurrencyStatus.SUPERSEDED.value
_MARKED_OUT_OF_FORCE = {"superseded", "repealed"}
_CASE_CHUNK_PREFIX = "case-chunk-"


@dataclass(frozen=True)
class CurrencyChange:
    document: CanonicalDocument
    previous_status: str
    previous_successor: str | None
    decision: CurrencyDecision

    @property
    def names(self) -> set[str]:
        return {
            name.strip().casefold()
            for name in (self.document.title, self.document.act_name)
            if name and name.strip()
        }

    @property
    def key(self) -> str:
        """One notice per answer per change, however many copies of the Act are held."""
        status = self.decision.status.value
        identity = "|".join(
            [sorted(self.names)[0], self.previous_status, status, self.decision.superseded_by or ""]
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def is_worth_telling_someone(
    previous_status: str, previous_successor: str | None, decision: CurrencyDecision
) -> bool:
    """A change someone relying on the law must hear about.

    Into or out of superseded, or a different successor. `unverified` to `in_force`
    is this system learning something, not the law changing, and telling people would
    bury the notices that matter.
    """
    status = decision.status.value
    if status == SUPERSEDED and previous_status == SUPERSEDED:
        return (decision.superseded_by or None) != (previous_successor or None)
    return SUPERSEDED in {status, previous_status} and status != previous_status


def citation_needs_notice(citation: dict[str, Any], change: CurrencyChange) -> bool:
    """Whether the answer told its reader something this change makes out of date."""
    name_matches = any(
        str(citation.get(field) or "").strip().casefold() in change.names
        for field in ("title", "act_name")
    )
    if not name_matches or str(citation.get("chunk_id") or "").startswith(_CASE_CHUNK_PREFIX):
        return False
    marked_out_of_force = citation.get("current_status") in _MARKED_OUT_OF_FORCE
    if change.decision.status is CurrencyStatus.SUPERSEDED:
        # The answer already said so, and named this successor or none at all.
        recorded_successor = citation.get("replaced_by")
        return not marked_out_of_force or bool(
            recorded_successor
            and change.decision.superseded_by
            and recorded_successor != change.decision.superseded_by
        )
    # Out of superseded: only an answer that called it repealed is now wrong.
    return marked_out_of_force


def _load_documents() -> list[CanonicalDocument] | None:
    path = Path(settings.legal_kb_root) / "metadata" / "canonical_documents.jsonl"
    if not path.is_file():
        return None
    return list(iter_canonical_documents(load_manifest(path)))


async def _messages_citing(
    session: AsyncSession, names: set[str]
) -> list[tuple[uuid.UUID, uuid.UUID, list[dict[str, Any]]]]:
    matches = text(
        "EXISTS (SELECT 1 FROM jsonb_array_elements(chat_messages.citations) AS cited "
        "WHERE lower(cited->>'title') = ANY(:names) OR lower(cited->>'act_name') = ANY(:names))"
    ).bindparams(bindparam("names", value=sorted(names), type_=ARRAY(Text)))
    rows = await session.execute(
        select(ChatMessage.id, ChatSession.user_id, ChatMessage.citations)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .where(ChatMessage.role == ChatMessageRole.ASSISTANT, matches)
    )
    return [(row[0], row[1], row[2]) for row in rows.all()]


async def sync_currency_notices(session: AsyncSession) -> dict[str, Any]:
    """Compare every document's currency with what was last seen, and write notices.

    The first run only records, because there is nothing to compare with and the whole
    corpus would otherwise read as changed. A manifest that cannot be found changes
    nothing: an unmounted volume is not every Act being repealed. Commits on success.
    """
    if not await session.scalar(select(func.pg_try_advisory_xact_lock(SYNC_LOCK_KEY))):
        return {"status": "skipped", "reason": "another instance is syncing"}

    documents = await asyncio.to_thread(_load_documents)
    if documents is None:
        await session.rollback()
        return {"status": "skipped", "reason": "no manifest at the configured path"}

    # A long-running process otherwise keeps the table it read at startup, and an
    # edit to it could never be seen as a change.
    currency._entries.cache_clear()

    stored = {
        row.canonical_document_id: row
        for row in (await session.scalars(select(DocumentCurrencyState))).all()
    }
    baseline = not stored
    changes: list[CurrencyChange] = []
    updated = 0
    for document in documents:
        decision = _currency(document)
        status = decision.status.value
        successor = decision.superseded_by
        state = stored.get(document.canonical_document_id)
        if state is None:
            session.add(
                DocumentCurrencyState(
                    canonical_document_id=document.canonical_document_id,
                    status=status,
                    superseded_by=successor,
                )
            )
            continue
        if state.status == status and (state.superseded_by or None) == (successor or None):
            continue
        if is_worth_telling_someone(state.status, state.superseded_by, decision):
            changes.append(CurrencyChange(document, state.status, state.superseded_by, decision))
        state.status = status
        state.superseded_by = successor
        updated += 1

    written = 0
    if changes:
        names = set().union(*(change.names for change in changes))
        for message_id, user_id, citations in await _messages_citing(session, names):
            for change in changes:
                if not any(citation_needs_notice(citation, change) for citation in citations):
                    continue
                result = await session.execute(
                    insert(LawChangeNotice)
                    .values(
                        id=uuid.uuid4(),
                        user_id=user_id,
                        message_id=message_id,
                        canonical_document_id=change.document.canonical_document_id,
                        document_title=change.document.title[:500],
                        previous_status=change.previous_status,
                        current_status=change.decision.status.value,
                        superseded_by=change.decision.superseded_by,
                        effective=change.decision.effective,
                        basis=change.decision.basis or None,
                        change_key=change.key,
                    )
                    .on_conflict_do_nothing(constraint="uq_law_change_notice_message_change")
                )
                written += int(result.rowcount or 0)

    outcome = {
        "status": "baseline" if baseline else "ran",
        "documents": len(documents),
        "status_changes": updated,
        "changes_to_notify": len(changes),
        "notices_written": written,
    }
    if baseline or updated:
        session.add(
            AuditLog(
                user_id=None,
                action="corpus.currency_sync",
                resource_type="document_currency_state",
                resource_id=None,
                metadata_=outcome,
            )
        )
    await session.commit()
    return outcome


# ----------------------------------------------------------- what a person sees


async def notices_for(session: AsyncSession, user_id: uuid.UUID, *, limit: int = 50) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(LawChangeNotice, ChatSession.id, ChatSession.title)
            .join(ChatMessage, ChatMessage.id == LawChangeNotice.message_id)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            # Both ends, so a notice can never be read through a conversation that
            # stopped being this person's.
            .where(LawChangeNotice.user_id == user_id, ChatSession.user_id == user_id)
            .order_by(LawChangeNotice.read_at.is_not(None), LawChangeNotice.created_at.desc())
            .limit(limit)
        )
    ).all()
    unread = await session.scalar(
        select(func.count())
        .select_from(LawChangeNotice)
        .where(LawChangeNotice.user_id == user_id, LawChangeNotice.read_at.is_(None))
    )
    return {
        "unread": int(unread or 0),
        "notices": [
            {
                "id": str(notice.id),
                "document_title": notice.document_title,
                "previous_status": notice.previous_status,
                "current_status": notice.current_status,
                "superseded_by": notice.superseded_by,
                "effective": notice.effective,
                "basis": notice.basis,
                "conversation_id": str(conversation_id),
                "conversation_title": conversation_title,
                "created_at": notice.created_at.isoformat(),
                "read_at": notice.read_at.isoformat() if notice.read_at else None,
            }
            for notice, conversation_id, conversation_title in rows
        ],
    }


async def mark_read(session: AsyncSession, user_id: uuid.UUID, notice_id: uuid.UUID) -> None:
    """A notice that is someone else's is reported exactly as one that does not exist."""
    owned = await session.scalar(
        select(LawChangeNotice.id).where(
            LawChangeNotice.id == notice_id, LawChangeNotice.user_id == user_id
        )
    )
    if owned is None:
        raise HTTPException(status_code=404, detail="Notice not found")
    await session.execute(
        update(LawChangeNotice)
        .where(LawChangeNotice.id == notice_id, LawChangeNotice.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    await session.commit()


async def mark_all_read(session: AsyncSession, user_id: uuid.UUID) -> int:
    result = await session.execute(
        update(LawChangeNotice)
        .where(LawChangeNotice.user_id == user_id, LawChangeNotice.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    await session.commit()
    return int(result.rowcount or 0)
