#!/usr/bin/env python3
"""Refuse a corpus cutover when a currency warning did not reach the index.

Two fields recorded in the canonical manifest never reached a reader, each for
the same reason: the chunk had no field for them, so they were dropped one hop
before the retrieval payload while four separate citation surfaces asked for
them.

  source_url      1,026 of 1,036 documents recorded one; 0 of 200 sampled
                  points in the live index carried it. Every citation named a
                  provision and gave the reader no way to open it.
  currency_note   1,164 of 1,566 documents record why a document's currency is
                  in doubt. None of them reached a reader, so both lanes said
                  "the current-law status of one or more retrieved records is
                  not verified" for an Act whose commencement notification was
                  never located, for a rules consolidation with a known later
                  amendment chain, and for a circular nobody had got round to
                  checking.

Both are fixed in the ingestion path. This is the gate that keeps them fixed:
a payload field that silently stops being written is invisible from the
outside, and the symptom -- a generic warning instead of a specific one -- is
something a reader notices and an engineer does not.

It also pins the instruments that are individually known to be doubtful.
`--warned` takes a title fragment and a keyword that must appear in that
document's note, so a document flagged for one reason cannot quietly acquire a
different one.

Read-only. It scrolls payloads and writes nothing.

Usage:
    python scripts/check_currency_payload_gate.py --collection global_legal_corpus_v5
    python scripts/check_currency_payload_gate.py --collection global_legal_corpus_v5 \
        --require-complete
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

MANIFEST = ROOT / "data" / "legal_kb" / "metadata" / "canonical_documents.jsonl"

# Instruments flagged individually during acquisition. Each is a title fragment
# and a word that must appear in the recorded reason, so a document warned
# about its commencement cannot silently come to be warned about something
# else instead.
DEFAULT_WARNED: tuple[tuple[str, str], ...] = (
    ("Andhra Pradesh Residential and Non-Residential Premises Tenancy", "commencement"),
    ("Central Motor Vehicles Rules, 1989", "amendment"),
)

# A currency warning is only meaningful if the document is not also claiming to
# be settled law.
CURRENT_STATUSES_THAT_MUST_NOT_APPLY = {"current", "in force", "operative"}


def manifest_documents() -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    with MANIFEST.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                documents[str(row.get("document_id"))] = row
    return documents


async def indexed_payloads(collection: str) -> dict[str, dict[str, Any]]:
    """One representative payload per indexed document."""
    from app.core.qdrant import create_qdrant_client

    client = create_qdrant_client()
    representative: dict[str, dict[str, Any]] = {}
    try:
        offset = None
        while True:
            points, offset = await client.scroll(
                collection_name=collection,
                limit=1000,
                offset=offset,
                with_payload=[
                    "document_id",
                    "title",
                    "source_url",
                    "currency_note",
                    "is_current",
                    "is_superseded",
                ],
                with_vectors=False,
            )
            for point in points:
                payload = dict(point.payload or {})
                document_id = str(payload.get("document_id") or "")
                representative.setdefault(document_id, payload)
            if offset is None:
                break
    finally:
        await client.close()
    return representative


def check(
    documents: dict[str, dict[str, Any]],
    payloads: dict[str, dict[str, Any]],
    warned: tuple[tuple[str, str], ...],
    *,
    require_complete: bool,
) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    indexed = set(payloads) & set(documents)

    with_note = [key for key in indexed if str(documents[key].get("currency_note") or "").strip()]
    with_url = [key for key in indexed if str(documents[key].get("source_url") or "").strip()]
    note_missing = [key for key in with_note if not str(payloads[key].get("currency_note") or "").strip()]
    url_missing = [key for key in with_url if not str(payloads[key].get("source_url") or "").strip()]
    key_absent = [key for key in indexed if "currency_note" not in payloads[key]]

    summary: dict[str, Any] = {
        "collection_documents_indexed": len(indexed),
        "manifest_documents": len(documents),
        "documents_with_a_recorded_note": len(with_note),
        "notes_missing_from_the_index": len(note_missing),
        "documents_with_a_recorded_url": len(with_url),
        "urls_missing_from_the_index": len(url_missing),
        "payloads_without_the_currency_note_key": len(key_absent),
    }

    if key_absent:
        failures.append(
            f"{len(key_absent)} indexed document(s) have no currency_note key at all; "
            "they were written by an ingestion that predates the field, so a resume "
            "skipped them. Rebuild rather than resume."
        )
    if note_missing:
        names = ", ".join(str(documents[key].get("title") or key)[:48] for key in note_missing[:3])
        failures.append(
            f"{len(note_missing)} document(s) record a currency warning that is absent "
            f"from their indexed payload, including: {names}"
        )
    if url_missing:
        names = ", ".join(str(documents[key].get("title") or key)[:48] for key in url_missing[:3])
        failures.append(
            f"{len(url_missing)} document(s) record an official URL that is absent from "
            f"their indexed payload, including: {names}"
        )

    # The individually flagged instruments.
    for fragment, keyword in warned:
        matches = [
            key
            for key, row in documents.items()
            if fragment.lower() in str(row.get("title") or "").lower()
        ]
        if not matches:
            failures.append(f"'{fragment}' is not in the canonical manifest at all")
            continue
        for key in matches:
            title = str(documents[key].get("title") or key)[:56]
            note = str(documents[key].get("currency_note") or "")
            if keyword not in note.lower():
                failures.append(
                    f"{title}: its recorded reason no longer mentions '{keyword}'. "
                    "The warning this gate was written for has changed; re-read it "
                    "before changing this gate."
                )
            if key not in payloads:
                if require_complete:
                    failures.append(f"{title}: flagged as doubtful and not indexed")
                else:
                    summary.setdefault("warned_not_yet_indexed", []).append(title)
                continue
            payload = payloads[key]
            if not str(payload.get("currency_note") or "").strip():
                failures.append(f"{title}: indexed with no currency warning")
            elif keyword not in str(payload["currency_note"]).lower():
                failures.append(
                    f"{title}: indexed warning does not mention '{keyword}'"
                )
            if payload.get("is_current") is True:
                failures.append(
                    f"{title}: indexed as current law while its currency is in doubt"
                )
            status = str(documents[key].get("current_status") or "").strip().lower()
            if status in CURRENT_STATUSES_THAT_MUST_NOT_APPLY:
                failures.append(
                    f"{title}: current_status is '{status}', which asserts settled law"
                )
            summary.setdefault("warned_verified", []).append(title)

    if require_complete and len(indexed) < len(documents):
        failures.append(
            f"only {len(indexed)} of {len(documents)} manifest documents are indexed; "
            "the build is incomplete"
        )
    return failures, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--collection", required=True)
    parser.add_argument(
        "--warned",
        nargs="*",
        metavar="TITLE_FRAGMENT=KEYWORD",
        help="Override the flagged instruments, as 'fragment=keyword' pairs",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Also fail when the build is unfinished. Use before a cutover, not during a build.",
    )
    args = parser.parse_args()

    if not MANIFEST.exists():
        print(f"No manifest at {MANIFEST}", file=sys.stderr)
        return 2

    warned = DEFAULT_WARNED
    if args.warned:
        parsed: list[tuple[str, str]] = []
        for item in args.warned:
            fragment, _, keyword = item.partition("=")
            if not fragment or not keyword:
                print(f"--warned expects 'fragment=keyword', got {item!r}", file=sys.stderr)
                return 2
            parsed.append((fragment, keyword))
        warned = tuple(parsed)

    documents = manifest_documents()
    payloads = asyncio.run(indexed_payloads(args.collection))
    failures, summary = check(documents, payloads, warned, require_complete=args.require_complete)

    print(json.dumps(summary, indent=2, sort_keys=True))
    if failures:
        print("\nCurrency payload gate FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("\nCurrency payload gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
