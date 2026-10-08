#!/usr/bin/env python3
"""Give every indexed passage the official URL its document already records.

The canonical manifest holds a source URL for 1,026 of its 1,036 documents.
None of them reached a reader: `LegalChunk` had no such field, so the chunker
dropped it, so the retrieval payload never carried the key -- while Fast,
Deep, the interim source list and the defence strategy agent all read
`payload.get("source_url")`. Measured against the live index: 0 of 200
sampled points had it. A citizen was shown "BNSS section 35 provides X" with
no way to go and read section 35.

The code path is fixed, so anything ingested from now on carries it. This
backfills what is already indexed, and it is a payload-only update: it sets
one key by document id and never touches a vector, so there is no
re-embedding and no re-chunking. A full re-ingestion would also do it, at the
cost of hours and a rebuilt index.

THIS MUTATES A QDRANT COLLECTION. It must not run while another agent is
collecting or ingesting -- see docs/evidence/corpus/ACQUISITION_HANDOFF.md.
It refuses to write without --confirm, reports what it would do first, and
writes nothing but the one key.

Usage:
    python scripts/backfill_source_urls.py --collection global_legal_corpus_v4
    python scripts/backfill_source_urls.py --collection global_legal_corpus_v4 --confirm
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

MANIFEST = ROOT / "data" / "legal_kb" / "metadata" / "canonical_documents.jsonl"

# Keyed on the id the payload actually carries. canonical_document_id groups
# duplicates of one instrument, which is the wrong granularity here: two
# copies of an Act from two ministries have different official URLs.
PAYLOAD_KEY = "document_id"


def urls_by_document() -> dict[str, str]:
    urls: dict[str, str] = {}
    with MANIFEST.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            document = json.loads(line)
            url = str(document.get("source_url") or "").strip()
            document_id = str(document.get("document_id") or "").strip()
            if url and document_id and url.startswith("http"):
                urls[document_id] = url
    return urls


async def run(args: argparse.Namespace) -> int:
    from qdrant_client import models

    from app.core.qdrant import create_qdrant_client

    urls = urls_by_document()
    print(f"{len(urls)} documents in the manifest carry an official URL")

    client = create_qdrant_client()
    try:
        info = await client.get_collection(args.collection)
        print(f"{args.collection}: {info.points_count} points, status {info.status}")

        counts: Counter[str] = Counter()
        offset = None
        seen_documents: set[str] = set()
        while True:
            points, offset = await client.scroll(
                collection_name=args.collection,
                limit=1000,
                offset=offset,
                with_payload=[PAYLOAD_KEY, "source_url"],
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                document_id = str(payload.get(PAYLOAD_KEY) or "")
                seen_documents.add(document_id)
                if payload.get("source_url"):
                    counts["already_set"] += 1
                elif document_id in urls:
                    counts["would_set"] += 1
                else:
                    counts["no_url_in_manifest"] += 1
            if offset is None:
                break
        print(json.dumps(dict(counts), indent=2, sort_keys=True))
        print(
            f"{len(seen_documents & set(urls))} of {len(seen_documents)} "
            "indexed documents are matched by the manifest"
        )

        if not args.confirm:
            print(
                "\nDry run. Nothing was written. Re-run with --confirm, and only when no "
                "collection or ingestion work is in progress."
            )
            return 0

        written = 0
        for document_id, url in urls.items():
            if document_id not in seen_documents:
                continue
            await client.set_payload(
                collection_name=args.collection,
                payload={"source_url": url},
                points=models.Filter(
                    must=[
                        models.FieldCondition(
                            key=PAYLOAD_KEY, match=models.MatchValue(value=document_id)
                        )
                    ]
                ),
                wait=True,
            )
            written += 1
            if written % 100 == 0:
                print(f"  {written} documents updated", flush=True)
        print(f"Set source_url on the points of {written} documents.")
        return 0
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--collection", required=True)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually write. Never while another agent is collecting or ingesting.",
    )
    args = parser.parse_args()
    if not MANIFEST.exists():
        print(f"No manifest at {MANIFEST}", file=sys.stderr)
        return 2
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
