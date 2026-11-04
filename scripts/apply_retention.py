#!/usr/bin/env python3
"""Erase conversations past CHAT_RETENTION_DAYS. For a daily cron job.

Run from the repository with the backend's environment:

    PYTHONPATH=backend python scripts/apply_retention.py [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services import privacy


async def main(dry_run: bool) -> None:
    days = settings.chat_retention_days
    async with AsyncSessionLocal() as session:
        due = await privacy.expired_conversation_ids(session, days=days)
        erased = 0
        if not dry_run:
            erased = await privacy.apply_retention(session)
            await session.commit()
    print(json.dumps({"chat_retention_days": days, "past_retention": len(due), "erased": erased}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Count without erasing.")
    asyncio.run(main(parser.parse_args().dry_run))
