"""The daily background passes: conversation retention and currency notices.

Retention applies `chat_retention_days` and nothing else. It stays off at the
default of 0, which means keep. The console's purge categories remain manual,
because a purge consumes a dry run that a person read.

Two guards keep several API instances, and restarts, from repeating work. A
PostgreSQL advisory lock is held for the pass's transaction, and an audit row records
each run so a pass that ran recently is not run again. A failed pass is logged by
exception type only and the loop carries on: nothing here may take the API down.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models import AuditLog
from app.services import law_changes, privacy

logger = logging.getLogger("legal_rag.scheduled")

# This pass's slot in PostgreSQL's advisory lock space. Arbitrary but fixed.
RETENTION_LOCK_KEY = 720_410_602
RETENTION_PASS_ACTION = "privacy.retention_pass"
PASS_INTERVAL = timedelta(hours=24)
# Wake often enough to catch a due pass soon after one is missed. The audit row, not
# this sleep, decides whether a pass is due, so a restart neither repeats nor skips.
WAKE_SECONDS = 3600
# Let startup finish before touching the database.
STARTUP_DELAY_SECONDS = 60


async def run_retention_pass(*, now: datetime | None = None) -> dict[str, Any]:
    """One guarded run. Commits its own transaction, which also releases the lock."""
    days = settings.chat_retention_days
    if days <= 0:
        return {"status": "off"}
    current = now or datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        if not await session.scalar(select(func.pg_try_advisory_xact_lock(RETENTION_LOCK_KEY))):
            return {"status": "locked"}
        last = await session.scalar(
            select(func.max(AuditLog.timestamp)).where(AuditLog.action == RETENTION_PASS_ACTION)
        )
        if last is not None and current - last < PASS_INTERVAL:
            return {"status": "not_due"}
        erased = await privacy.apply_retention(session, days=days)
        session.add(
            AuditLog(
                user_id=None,
                action=RETENTION_PASS_ACTION,
                resource_type="chat_session",
                resource_id=None,
                metadata_={"erased": erased, "days": days},
            )
        )
        await session.commit()
    logger.info("retention pass: erased=%s days=%s", erased, days)
    return {"status": "ran", "erased": erased}


async def run_currency_pass() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        return await law_changes.sync_currency_notices(session)


_PASSES = (("retention", run_retention_pass), ("currency", run_currency_pass))


async def run_guarded(name: str, run: Any) -> dict[str, Any] | None:
    """Run one pass. An exception ends here. Cancellation does not."""
    try:
        return await run()
    except Exception as exc:  # noqa: BLE001 - a failed pass must not end the loop
        # The type only: a message can carry a host or a row.
        logger.error("scheduled pass failed: %s: %s", name, type(exc).__name__)
        return None


async def _loop() -> None:
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    last_currency: datetime | None = None
    while True:
        await run_guarded("retention", run_retention_pass)
        current = datetime.now(timezone.utc)
        if last_currency is None or current - last_currency >= PASS_INTERVAL:
            await run_guarded("currency", run_currency_pass)
            last_currency = current
        await asyncio.sleep(WAKE_SECONDS)


_task: asyncio.Task[None] | None = None


async def start() -> None:
    global _task
    if _task is None:
        _task = asyncio.create_task(_loop(), name="scheduled-passes")


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        with suppress(asyncio.CancelledError):
            await _task
        _task = None
