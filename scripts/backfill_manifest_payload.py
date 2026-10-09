#!/usr/bin/env python3
"""Repair citation and currency payload fields without rebuilding vectors.

The canonical manifest can be corrected while a long rebuild is running, but
the worker has already loaded its copy of that manifest. Documents written by
that worker therefore keep the old metadata even though their vectors and text
are valid. Re-embedding them would waste hours and could change retrieval for
no semantic reason.

This script compares every indexed point with the canonical manifest and can
repair only the payload fields that do not affect embeddings:

* ``source_url``
* ``currency_note``
* ``verified_official``
* ``source_type``

It is a dry run unless ``--confirm`` is present. A write is refused while an
ingestion worker is alive so the comparison cannot race the rebuild.

Usage:
    python scripts/backfill_manifest_payload.py --collection global_legal_corpus_v5
    python scripts/backfill_manifest_payload.py --collection global_legal_corpus_v5 --confirm
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

MANIFEST = ROOT / "data" / "legal_kb" / "metadata" / "canonical_documents.jsonl"
FIELDS = ("source_url", "currency_note", "verified_official", "source_type")
BATCH = 256


def ingestion_running() -> bool:
    result = subprocess.run(
        ["pgrep", "-f", "app.ingestion.pipeline"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def manifest_payloads() -> dict[str, dict[str, Any]]:
    from app.ingestion.metadata import iter_canonical_documents, load_manifest

    documents = iter_canonical_documents(load_manifest(MANIFEST))
    return {
        document.canonical_document_id: {
            "source_url": document.source_url or "",
            "currency_note": document.currency_note or "",
            "verified_official": document.verified_official,
            "source_type": document.resolved_type().value,
        }
        for document in documents
    }


def payload_difference(
    actual: dict[str, Any], desired: dict[str, Any]
) -> dict[str, Any]:
    return {
        field: desired[field]
        for field in FIELDS
        if actual.get(field) != desired[field]
    }


async def run(*, collection: str, confirm: bool) -> int:
    from app.core.qdrant import create_qdrant_client

    if confirm and ingestion_running():
        print(
            "refusing to write while an ingestion worker is alive; run this after "
            "the rebuild completes",
            file=sys.stderr,
        )
        return 2

    desired_by_document = manifest_payloads()
    mismatches: dict[str, list[Any]] = defaultdict(list)
    mismatch_fields: Counter[str] = Counter()
    indexed_documents: set[str] = set()
    unmatched_points = 0
    scanned = 0

    client = create_qdrant_client()
    try:
        info = await client.get_collection(collection)
        print(f"{collection}: {info.points_count:,} points, status {info.status}")

        offset = None
        while True:
            points, offset = await client.scroll(
                collection_name=collection,
                limit=1000,
                offset=offset,
                with_payload=["canonical_document_id", *FIELDS],
                with_vectors=False,
            )
            for point in points:
                scanned += 1
                payload = dict(point.payload or {})
                canonical_id = str(payload.get("canonical_document_id") or "")
                desired = desired_by_document.get(canonical_id)
                if desired is None:
                    unmatched_points += 1
                    continue
                indexed_documents.add(canonical_id)
                difference = payload_difference(payload, desired)
                if not difference:
                    continue
                for field in difference:
                    mismatch_fields[field] += 1
                key = json.dumps(difference, sort_keys=True, ensure_ascii=False)
                mismatches[key].append(point.id)
            if offset is None:
                break

        mismatch_points = sum(len(ids) for ids in mismatches.values())
        print(
            json.dumps(
                {
                    "scanned_points": scanned,
                    "indexed_documents": len(indexed_documents),
                    "manifest_documents": len(desired_by_document),
                    "unmatched_points": unmatched_points,
                    "mismatch_points": mismatch_points,
                    "mismatches_by_field": dict(sorted(mismatch_fields.items())),
                },
                indent=2,
                sort_keys=True,
            )
        )

        if not confirm:
            print("\nDry run. Nothing was written; add --confirm after ingestion stops.")
            return 0

        written = 0
        for encoded, ids in mismatches.items():
            update = json.loads(encoded)
            for start in range(0, len(ids), BATCH):
                batch = ids[start : start + BATCH]
                await client.set_payload(
                    collection_name=collection,
                    payload=update,
                    points=batch,
                    wait=True,
                )
                written += len(batch)
        print(f"Repaired {written:,} points without changing vectors or text.")
        return 0
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--confirm", action="store_true")
    arguments = parser.parse_args()
    if not MANIFEST.is_file():
        print(f"manifest not found: {MANIFEST}", file=sys.stderr)
        return 2
    return asyncio.run(run(collection=arguments.collection, confirm=arguments.confirm))


if __name__ == "__main__":
    raise SystemExit(main())
