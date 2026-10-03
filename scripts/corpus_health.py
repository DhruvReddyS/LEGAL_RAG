#!/usr/bin/env python3
"""Check the canonical manifest against the files and against itself.

Acquisition, promotion and ingestion all write here, and a manifest that has
drifted from the files on disk produces retrieval failures that look like
model problems. This finds the drift.

    python scripts/corpus_health.py           # report
    python scripts/corpus_health.py --check   # exit 1 if anything is wrong

Checks, each reported with the rows it affects:
  missing file        a row whose local_path is not on disk
  duplicate id        two rows sharing a canonical_document_id
  duplicate checksum  two rows with the same sha256 under different ids
  empty title         a row with no title, or a title shorter than 8 characters
  bad jurisdiction    a jurisdiction outside the recorded vocabulary
  bad currency        a current_status outside the recorded vocabulary
  no source           a row with neither a source URL nor a recorded authority
  unreadable          a row whose file cannot be opened as a PDF
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "data/legal_kb"
MANIFEST = LIB / "metadata/canonical_documents.jsonl"

JURISDICTIONS = {"India - Central", "India - Andhra Pradesh", "India - Telangana"}
CURRENCY = {"current/verify", "superseded", "repealed", "precedential/verify"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="exit non-zero on any finding")
    parser.add_argument("--open-pdfs", action="store_true",
                        help="also open every PDF, which is slow")
    args = parser.parse_args()

    rows = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    findings: dict[str, list[str]] = collections.defaultdict(list)

    by_id = collections.Counter(r.get("canonical_document_id") for r in rows)
    by_sum = collections.defaultdict(set)
    for row in rows:
        by_sum[row.get("sha256")].add(row.get("canonical_document_id"))

    for row in rows:
        name = (row.get("title") or row.get("original_filename") or "?")[:60]
        path = LIB / (row.get("local_path") or "")
        if not row.get("local_path") or not path.is_file():
            findings["missing file"].append(name)
        if by_id[row.get("canonical_document_id")] > 1:
            findings["duplicate id"].append(name)
        if len(by_sum.get(row.get("sha256")) or ()) > 1:
            findings["duplicate checksum"].append(name)
        if len((row.get("title") or "").strip()) < 8:
            findings["empty title"].append(row.get("original_filename") or "?")
        if row.get("jurisdiction") not in JURISDICTIONS:
            findings["bad jurisdiction"].append(f"{name} -> {row.get('jurisdiction')!r}")
        if row.get("current_status") not in CURRENCY:
            findings["bad currency"].append(f"{name} -> {row.get('current_status')!r}")
        if not row.get("source_url") and not row.get("authority"):
            findings["no source"].append(name)

    if args.open_pdfs:
        import pymupdf as fitz
        for row in rows:
            path = LIB / (row.get("local_path") or "")
            if not path.is_file():
                continue
            try:
                with fitz.open(path) as doc:
                    if len(doc) == 0:
                        findings["unreadable"].append(path.name)
            except Exception as error:
                findings["unreadable"].append(f"{path.name}: {type(error).__name__}")

    unique = len({r.get("canonical_document_id") for r in rows})
    pages = sum(r.get("page_count") or 0 for r in rows)
    print(f"{len(rows)} rows, {unique} canonical documents, {pages:,} pages")
    if not findings:
        print("no findings")
        return 0
    for kind, items in sorted(findings.items(), key=lambda kv: -len(kv[1])):
        print(f"\n{kind}: {len(items)}")
        for item in sorted(set(items))[:8]:
            print(f"   {item}")
        if len(set(items)) > 8:
            print(f"   ... and {len(set(items)) - 8} more")
    return 1 if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
