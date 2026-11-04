"""The corpus coverage browser and its work lists.

The manifest is what the corpus is meant to contain, including what is held back,
so it can answer "what do we have and what state is it in" without touching the
serving index. Corpus metadata is public law: no private case material passes
through here, and there is no text search over chunks.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ingestion.metadata import CanonicalDocument, iter_canonical_documents, load_manifest
from app.models import AuditLog, User
from app.models.admin_tools import CorpusWorkItem, DocumentQuarantine

QUEUES = ("ocr", "verification", "currency")
_VERIFIED_QUALITY = {"verified", "ok", "admin_validated"}


def currency_flag(document: CanonicalDocument) -> str:
    """The same reading the answer lanes use: unverified unless it says otherwise.

    "current/verify" is not current. Reading it as such here would tell an
    administrator a document has nothing to check when the corpus says it does.
    """
    if document.is_superseded:
        return "repealed_or_superseded"
    if document.currency_note:
        return "warned"
    if document.is_current:
        return "current"
    return "unverified"


def document_queues(document: CanonicalDocument) -> list[str]:
    queues: list[str] = []
    if document.ocr_required:
        queues.append("ocr")
    if not document.verified_official or document.quality_status not in _VERIFIED_QUALITY:
        queues.append("verification")
    if currency_flag(document) in {"warned", "unverified"}:
        queues.append("currency")
    return queues


@dataclass(frozen=True)
class _Row:
    document: CanonicalDocument
    flag: str
    queues: tuple[str, ...]
    haystack: str


_cache: tuple[Path, float, list[_Row]] | None = None


def _manifest_rows() -> list[_Row]:
    global _cache
    path = Path(settings.legal_kb_root) / "metadata" / "canonical_documents.jsonl"
    if not path.is_file():
        return []
    modified = path.stat().st_mtime
    if _cache is not None and _cache[0] == path and _cache[1] == modified:
        return _cache[2]
    rows = [
        _Row(
            document=document,
            flag=currency_flag(document),
            queues=tuple(document_queues(document)),
            haystack=" ".join(
                part
                for part in (
                    document.title,
                    document.act_name,
                    document.category,
                    document.authority,
                    document.court,
                    document.canonical_document_id,
                )
                if part
            ).casefold(),
        )
        for document in iter_canonical_documents(load_manifest(path))
    ]
    _cache = (path, modified, rows)
    return rows


def _domain(category: str) -> str:
    return category.split("/", 1)[0] if category else "uncategorised"


def _matches(
    row: _Row,
    *,
    q: str,
    source_type: str | None,
    domain: str | None,
    currency: str | None,
    queue: str | None,
) -> bool:
    if q and q not in row.haystack:
        return False
    if source_type and row.document.source_type != source_type:
        return False
    if domain and _domain(row.document.category) != domain:
        return False
    if currency and row.flag != currency:
        return False
    if queue and queue not in row.queues:
        return False
    return True


def _facets(rows: list[_Row]) -> dict[str, Any]:
    return {
        "source_type": dict(Counter(row.document.source_type for row in rows).most_common()),
        "domain": dict(Counter(_domain(row.document.category) for row in rows).most_common()),
        "currency": dict(Counter(row.flag for row in rows).most_common()),
        "queue": {name: sum(1 for row in rows if name in row.queues) for name in QUEUES},
    }


async def browse_corpus(
    session: AsyncSession,
    *,
    q: str = "",
    source_type: str | None = None,
    domain: str | None = None,
    currency: str | None = None,
    queue: str | None = None,
    work_status: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    rows = await asyncio.to_thread(_manifest_rows)
    needle = q.strip().casefold()
    matched = [
        row
        for row in rows
        if _matches(
            row, q=needle, source_type=source_type, domain=domain, currency=currency, queue=queue
        )
    ]
    quarantined = {
        row.canonical_document_id: row
        for row in (
            await session.scalars(
                select(DocumentQuarantine).where(DocumentQuarantine.released_at.is_(None))
            )
        ).all()
    }
    items = list(
        (
            await session.scalars(select(CorpusWorkItem).where(CorpusWorkItem.queue == queue))
        ).all()
    ) if queue else []
    work_by_document = {item.canonical_document_id: item for item in items}
    if queue and work_status:
        matched = [
            row
            for row in matched
            if (
                work_by_document[row.document.canonical_document_id].status
                if row.document.canonical_document_id in work_by_document
                else "open"
            )
            == work_status
        ]
    start = (page - 1) * page_size
    return {
        "total_documents": len(rows),
        "total_pages": sum(row.document.page_count for row in rows),
        "total": len(matched),
        "page": page,
        "page_size": page_size,
        "facets": _facets(rows),
        "quarantined": len(quarantined),
        "documents": [
            _document(row, quarantined, work_by_document.get(row.document.canonical_document_id))
            for row in matched[start : start + page_size]
        ],
    }


def _document(
    row: _Row,
    quarantined: dict[str, DocumentQuarantine],
    work: CorpusWorkItem | None,
) -> dict[str, Any]:
    document = row.document
    return {
        "canonical_document_id": document.canonical_document_id,
        "title": document.title,
        "source_type": document.source_type,
        "category": document.category,
        "domain": _domain(document.category),
        "jurisdiction": document.jurisdiction,
        "act_name": document.act_name,
        "court": document.court,
        "current_status": document.current_status,
        "currency_flag": row.flag,
        "currency_note": document.currency_note,
        "superseded_by": document.superseded_by,
        "verified_official": document.verified_official,
        "quality_status": document.quality_status,
        "ocr_required": bool(document.ocr_required),
        "page_count": document.page_count,
        "source_url": document.source_url,
        "queues": list(row.queues),
        "quarantined": document.canonical_document_id in quarantined,
        "work_status": work.status if work else "open",
        "work_note": work.note if work else None,
    }


def manifest_document(canonical_document_id: str) -> CanonicalDocument | None:
    for row in _manifest_rows():
        if row.document.canonical_document_id == canonical_document_id:
            return row.document
    return None


async def set_work_item(
    session: AsyncSession,
    *,
    admin: User,
    canonical_document_id: str,
    queue: str,
    status: str,
    note: str | None,
) -> dict[str, Any]:
    document = await asyncio.to_thread(manifest_document, canonical_document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Not a document in the corpus manifest")
    if queue not in document_queues(document):
        raise HTTPException(status_code=409, detail="This document is not on that work list")
    item = await session.scalar(
        select(CorpusWorkItem).where(
            CorpusWorkItem.canonical_document_id == canonical_document_id,
            CorpusWorkItem.queue == queue,
        )
    )
    if item is None:
        item = CorpusWorkItem(canonical_document_id=canonical_document_id, queue=queue)
        session.add(item)
    item.status = status
    item.note = note
    item.updated_by = admin.id
    session.add(
        AuditLog(
            user_id=admin.id,
            action="admin.corpus.work_item",
            resource_type="corpus_document",
            metadata_={
                "canonical_document_id": canonical_document_id,
                "queue": queue,
                "status": status,
                "has_note": bool(note),
            },
        )
    )
    await session.commit()
    return {
        "canonical_document_id": canonical_document_id,
        "queue": queue,
        "status": status,
        "note": note,
    }
