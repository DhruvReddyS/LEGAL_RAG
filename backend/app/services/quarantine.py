"""Which corpus documents retrieval must not return right now.

`RetrievalFilters.to_qdrant` is synchronous and sits under every path into the
global corpus: Fast, Deep, drafting, defence analysis, document analysis and
citation following. Reading the set from memory lets that one choke point apply
the exclusion without any of those callers knowing about it.

The database is the source of truth. A change updates this process the moment it
commits, and a background refresh keeps any other process in step.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from sqlalchemy import select

logger = logging.getLogger("legal_rag.quarantine")

REFRESH_SECONDS = 15.0

_active: frozenset[str] = frozenset()
_refresher: asyncio.Task | None = None


def quarantined_document_ids() -> frozenset[str]:
    return _active


def is_quarantined(canonical_document_id: object) -> bool:
    return str(canonical_document_id) in _active


def replace_active(document_ids: frozenset[str]) -> None:
    global _active
    _active = document_ids


async def refresh() -> frozenset[str]:
    from app.core.database import AsyncSessionLocal
    from app.models.admin_tools import DocumentQuarantine

    async with AsyncSessionLocal() as session:
        rows = await session.scalars(
            select(DocumentQuarantine.canonical_document_id).where(
                DocumentQuarantine.released_at.is_(None)
            )
        )
        replace_active(frozenset(rows.all()))
    return _active


async def _refresh_forever() -> None:
    while True:
        await asyncio.sleep(REFRESH_SECONDS)
        try:
            await refresh()
        except Exception as exc:  # noqa: BLE001 - keep the last known set serving
            logger.warning("quarantine refresh failed: %s", type(exc).__name__)


async def start() -> None:
    """Load before serving. An unknown exclusion list must stop the boot.

    Serving with an empty set after a failed load would quietly return every
    document an administrator has withdrawn.
    """
    global _refresher
    await refresh()
    _refresher = asyncio.create_task(_refresh_forever())


async def stop() -> None:
    global _refresher
    if _refresher is not None:
        _refresher.cancel()
        with suppress(asyncio.CancelledError):
            await _refresher
        _refresher = None
