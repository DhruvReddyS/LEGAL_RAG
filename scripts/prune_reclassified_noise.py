#!/usr/bin/env python3
"""Remove indexed chunks that the current quality classifier rejects.

A long corpus build can start before a narrowly-scoped quality fix lands. The
vectors and all valid chunks remain usable, so rebuilding every document would
waste hours. This script re-runs the current deterministic classifier against
the indexed text and can delete only points now classified as noise.

The default is a dry run. A confirmed write is refused while any ingestion
worker is alive. Review the complete candidate list before confirming:

    python scripts/prune_reclassified_noise.py \
      --collection global_legal_corpus_v5 --sample-limit 10000
    python scripts/prune_reclassified_noise.py \
      --collection global_legal_corpus_v5 --confirm

Deleting from the configured live collection additionally requires
``--allow-live``. That escape hatch is for deliberate maintenance, not a
release-candidate promotion.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

BATCH = 256


def corpus_build_running() -> bool:
    """Return true for both a worker and a supervisor able to restart it."""
    for pattern in (
        "app.ingestion.pipeline",
        "rebuild_until_done.sh __loop",
        "scripts/run_rebuild.sh",
    ):
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return True
    return False


def reclassified_reason(payload: dict[str, Any]) -> str | None:
    """Return the new rejection reason for an indexed payload, if any."""
    from app.ingestion.enrichment import classify_quality

    if payload.get("quality") != "indexed":
        return None
    decision = classify_quality(
        str(payload.get("text") or ""),
        section=str(payload.get("section") or "") or None,
    )
    return decision.reason if not decision.indexed else None


async def run(
    *, collection: str, confirm: bool, sample_limit: int, allow_live: bool = False
) -> int:
    from qdrant_client import models

    from app.core.config import settings
    from app.core.qdrant import create_qdrant_client

    if confirm and corpus_build_running():
        print(
            "refusing to delete while a corpus rebuild worker or supervisor is "
            "alive; run this after the rebuild completes",
            file=sys.stderr,
        )
        return 2
    if confirm and collection == settings.qdrant_global_collection and not allow_live:
        print(
            f"refusing to delete from the configured live collection {collection!r}; "
            "use --allow-live only for deliberate live maintenance",
            file=sys.stderr,
        )
        return 2

    client = create_qdrant_client()
    try:
        info = await client.get_collection(collection)
        print(f"{collection}: {info.points_count:,} points, status {info.status}")

        point_ids: list[Any] = []
        reasons: Counter[str] = Counter()
        affected_documents: set[str] = set()
        samples: list[dict[str, Any]] = []
        scanned = 0
        offset = None
        while True:
            points, offset = await client.scroll(
                collection_name=collection,
                limit=1000,
                offset=offset,
                with_payload=[
                    "text",
                    "section",
                    "quality",
                    "canonical_document_id",
                    "chunk_id",
                    "title",
                ],
                with_vectors=False,
            )
            for point in points:
                scanned += 1
                payload = dict(point.payload or {})
                reason = reclassified_reason(payload)
                if reason is None:
                    continue
                point_ids.append(point.id)
                reasons[reason] += 1
                affected_documents.add(
                    str(payload.get("canonical_document_id") or "")
                )
                if len(samples) < sample_limit:
                    samples.append(
                        {
                            "point_id": str(point.id),
                            "chunk_id": payload.get("chunk_id"),
                            "canonical_document_id": payload.get(
                                "canonical_document_id"
                            ),
                            "title": payload.get("title"),
                            "section": payload.get("section"),
                            "reason": reason,
                            "text": payload.get("text"),
                        }
                    )
            if offset is None:
                break

        print(
            json.dumps(
                {
                    "scanned_points": scanned,
                    "reclassified_noise_points": len(point_ids),
                    "affected_documents": len(affected_documents),
                    "by_reason": dict(sorted(reasons.items())),
                    "samples": samples,
                    "sample_limit": sample_limit,
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
        )

        if not confirm:
            print("\nDry run. Nothing was deleted; review every candidate first.")
            return 0

        deleted = 0
        for start in range(0, len(point_ids), BATCH):
            batch = point_ids[start : start + BATCH]
            await client.delete(
                collection_name=collection,
                points_selector=models.PointIdsList(points=batch),
                wait=True,
            )
            deleted += len(batch)
        print(f"Deleted {deleted:,} reclassified noise points.")
        return 0
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--collection", required=True)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="permit a confirmed deletion from the configured serving collection",
    )
    parser.add_argument("--sample-limit", type=int, default=50)
    arguments = parser.parse_args()
    if arguments.sample_limit < 0:
        parser.error("--sample-limit must be zero or greater")
    return asyncio.run(
        run(
            collection=arguments.collection,
            confirm=arguments.confirm,
            sample_limit=arguments.sample_limit,
            allow_live=arguments.allow_live,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
