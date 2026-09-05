#!/usr/bin/env python3
"""Backfill resolved currency onto every point in a collection.

The live index holds `is_superseded: None` for all 25,517 points, because the
field was added after it was built. Seven guards read that field and every one
of them evaluates false forever.

Resumable by requirement, and it earns that: 25,517 points is a long enough
job that it will be interrupted, and the previous long job in this project was
killed twice -- once by a sandbox permission error and once by Docker stopping
underneath it. Progress is checkpointed after every batch, so a resume costs
one batch rather than the run.

Idempotent: re-running over already-migrated points writes the same values.
Currency is resolved by `app.services.currency`, which is a table lookup, so
the result depends only on the payload and the curated file -- never on when
the migration happened to run.

Usage:
    python scripts/migrate_currency_payload.py --dry-run
    python scripts/migrate_currency_payload.py
    python scripts/migrate_currency_payload.py --collection global_legal_corpus_v2
    python scripts/migrate_currency_payload.py --reset      # start over
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

BATCH = 256


def _checkpoint_path(collection: str) -> Path:
    from app.core.config import settings

    return Path(settings.legal_kb_root) / "logs" / f"currency_migration.{collection}.json"


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"offset": None, "scanned": 0, "written": 0, "counts": {}, "done": False}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_checkpoint(path: Path, state: dict[str, Any]) -> None:
    """Written whole, then moved into place.

    A checkpoint truncated by an interrupt is worse than none: the job would
    resume from a corrupt offset and skip a stretch of the collection silently.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _payload_update(payload: dict[str, Any]) -> dict[str, Any] | None:
    """The fields to set, or None when the point already says this."""
    from app.services.currency import resolve_currency

    decision = resolve_currency(payload)
    desired = {
        "currency_status": str(decision.status),
        "is_superseded": decision.is_superseded,
        "currency_source": decision.source,
        "saves_prior_conduct": decision.saves_prior_conduct,
    }
    if decision.superseded_by:
        desired["superseded_by"] = decision.superseded_by
    if decision.effective:
        desired["superseded_effective"] = decision.effective

    if all(payload.get(key) == value for key, value in desired.items()):
        return None
    return desired


async def migrate(*, collection: str, dry_run: bool, reset: bool) -> dict[str, Any]:
    from qdrant_client import models

    from app.core.qdrant import create_qdrant_client

    checkpoint_path = _checkpoint_path(collection)
    if reset and checkpoint_path.exists():
        checkpoint_path.unlink()
    state = _load_checkpoint(checkpoint_path)
    if state.get("done"):
        print(f"already complete for {collection}; --reset to run again")
        return state

    counts = Counter(state.get("counts", {}))
    client = create_qdrant_client()
    try:
        total = (await client.count(collection_name=collection, exact=True)).count
        print(f"{collection}: {total:,} points, resuming from offset {state['offset']!r}")

        offset = state["offset"]
        while True:
            points, offset = await client.scroll(
                collection_name=collection,
                limit=BATCH,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break

            for point in points:
                payload = dict(point.payload or {})
                state["scanned"] += 1
                update = _payload_update(payload)
                if update is None:
                    counts["unchanged"] += 1
                    continue
                counts[update["currency_status"]] += 1
                if dry_run:
                    continue
                await client.set_payload(
                    collection_name=collection,
                    payload=update,
                    points=[point.id],
                    wait=False,
                )
                state["written"] += 1

            state["offset"] = offset
            state["counts"] = dict(counts)
            if not dry_run:
                _save_checkpoint(checkpoint_path, state)
            print(
                f"  {state['scanned']:>7,}/{total:,}  written {state['written']:>7,}  "
                f"{dict(counts)}",
                flush=True,
            )
            if offset is None:
                break

        state["done"] = True
        state["completed_at"] = datetime.now(timezone.utc).isoformat()
        state["counts"] = dict(counts)
        if not dry_run:
            _save_checkpoint(checkpoint_path, state)
    finally:
        await client.close()
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true")
    arguments = parser.parse_args()

    from app.core.config import settings

    collection = arguments.collection or settings.qdrant_global_collection
    state = asyncio.run(
        migrate(collection=collection, dry_run=arguments.dry_run, reset=arguments.reset)
    )
    print("\n--- result ---")
    print(f"  scanned : {state['scanned']:,}")
    print(f"  written : {state['written']:,}")
    for status, count in sorted(state.get("counts", {}).items()):
        print(f"  {status:<14} {count:,}")
    if arguments.dry_run:
        print("\n  dry run: nothing was written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
