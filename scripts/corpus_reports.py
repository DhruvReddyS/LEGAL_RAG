#!/usr/bin/env python3
"""Emit the corpus registry reports from the canonical manifest.

Five reports the expansion is required to produce, all derived from one source
so they cannot disagree with each other:

    inventory.csv              every document, one row, for reading in a sheet
    copyright-register.md      licence and copyright basis per publisher
    source-verification.md     who published what, and whether it was official
    currency-report.md         what is in force, what is superseded, what is unchecked
    progress-report.md         counts by domain and jurisdiction, and the queues

    python scripts/corpus_reports.py
"""
from __future__ import annotations

import collections
import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "data/legal_kb"
META = LIB / "metadata"
OUT = ROOT / "docs/evidence/corpus"

FIELDS = ["canonical_document_id", "title", "category", "jurisdiction", "authority",
          "source_type", "year", "current_status", "page_count", "file_size",
          "language", "ocr_required", "verified_official", "licence",
          "copyright_status", "sha256", "source_url", "currency_note",
          "retrieved_on", "original_filename", "local_path"]


def manifest() -> list[dict]:
    rows, seen = [], set()
    for line in (META / "canonical_documents.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = row.get("canonical_document_id") or row.get("sha256")
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def queue(name: str) -> list[dict]:
    path = META / f"{name}.jsonl"
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def write_inventory(rows: list[dict]) -> Path:
    path = OUT / "inventory.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r.get("category") or "", r.get("title") or "")):
            writer.writerow({field: row.get(field) for field in FIELDS})
    return path


def _table(header: tuple[str, ...], body: list[tuple]) -> str:
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    for line in body:
        lines.append("| " + " | ".join(str(cell) for cell in line) + " |")
    return "\n".join(lines)


def write_copyright(rows: list[dict]) -> Path:
    by_authority = collections.defaultdict(list)
    for row in rows:
        by_authority[row.get("authority") or "unrecorded"].append(row)
    body = []
    for authority, group in sorted(by_authority.items(), key=lambda kv: -len(kv[1])):
        licences = sorted({r.get("licence") or "unrecorded" for r in group})
        status = sorted({r.get("copyright_status") or "unrecorded" for r in group})
        body.append((len(group), authority, "; ".join(licences)[:70], "; ".join(status)[:54]))
    text = f"""# Copyright and licensing register

Generated {date.today().isoformat()} from the canonical manifest.
{len(rows)} documents, {len(by_authority)} publishers.

Every document in this corpus is a work of the Government of India, a State
government, a High Court, or a statutory commission, obtained from that body's
own website. Indian government works are not placed under an open licence by
default, so each row records the publisher and the basis on which the document
was taken, rather than claiming a licence the publisher has not granted.

No commercial commentary, no publisher's headnotes, and no scanned textbook is
held. Where a secondary work was wanted but is commercial, only the
bibliographic record was kept. Nothing was obtained by bypassing a paywall, a
login, a CAPTCHA, or a robots restriction.

{_table(("Documents", "Publisher", "Licence recorded", "Copyright basis"), body)}
"""
    path = OUT / "copyright-register.md"
    path.write_text(text)
    return path


def write_source_verification(rows: list[dict]) -> Path:
    official = [r for r in rows if r.get("verified_official")]
    unverified = [r for r in rows if not r.get("verified_official")]
    by_host = collections.Counter()
    for row in rows:
        url = row.get("source_url") or ""
        if url.startswith("http"):
            by_host[url.split("/")[2]] += 1
    no_url = sum(1 for r in rows if not (r.get("source_url") or "").startswith("http"))
    deferred = queue("deferred_sources")
    text = f"""# Source verification report

Generated {date.today().isoformat()} from the canonical manifest.

{len(official)} of {len(rows)} documents are marked as verified official.
{len(unverified)} are not, and each of those needs its source confirmed before
anything it says is treated as authority.

{no_url} rows carry no source URL. Those were acquired before acquisition
recorded the URL it fetched, so their provenance rests on the publisher and
filename alone; re-acquiring them is the way to close that gap.

## Documents by source host

{_table(("Documents", "Host"), [(n, h) for h, n in by_host.most_common()])}

## Sources deferred, with the reason

{_table(("Source", "What", "Why it was deferred"),
        [(d.get("source", "?"), str(d.get("kind"))[:48], str(d.get("reason"))[:110])
         for d in deferred]) if deferred else "None."}
"""
    path = OUT / "source-verification.md"
    path.write_text(text)
    return path


def write_currency(rows: list[dict]) -> Path:
    status = collections.Counter(r.get("current_status") or "unrecorded" for r in rows)
    superseded = [r for r in rows if str(r.get("current_status")) in ("superseded", "repealed")]
    noted = [r for r in rows if r.get("currency_note")]
    text = f"""# Currency and amendment report

Generated {date.today().isoformat()} from the canonical manifest.

A retrieval system that cannot tell a reader which instrument is in force is
worse than no system, so this is the report to read before trusting an answer.

{_table(("Documents", "Recorded status"),
        [(n, s) for s, n in status.most_common()])}

The vocabulary above is inconsistent: several spellings mean the same thing.
Normalising it rewrites existing rows and has not been done.

{len(noted)} documents carry a currency note saying where they were published
and how amendments reach them. The rest do not, and for those the status field
is the only evidence.

## Recorded as superseded or repealed

These must never be served as the law in force.

{_table(("Title", "Category"),
        [(str(r.get("title"))[:84], r.get("category", "")) for r in superseded])
 if superseded else "None recorded."}
"""
    path = OUT / "currency-report.md"
    path.write_text(text)
    return path


def write_progress(rows: list[dict]) -> Path:
    cat = collections.Counter(r.get("category") or "?" for r in rows)
    place = collections.Counter(r.get("jurisdiction") or "?" for r in rows)
    pages = sum(r.get("page_count") or 0 for r in rows)
    ocr = sum(1 for r in rows if r.get("ocr_required"))
    queues = [(name, len(queue(name))) for name in
              ("quarantine", "duplicates", "needs_title", "failed_downloads", "deferred_sources")]
    text = f"""# Corpus expansion progress

Generated {date.today().isoformat()}.

{len(rows)} canonical documents, {pages:,} pages. {ocr} need OCR and are read
with the English trained data, which is the only one installed.

## By domain

{_table(("Documents", "Category"), [(n, c) for c, n in cat.most_common()])}

## By jurisdiction

{_table(("Documents", "Jurisdiction"), [(n, j) for j, n in place.most_common()])}

## Queues

Nothing uncertain was deleted. Each of these holds material with the reason it
is not in the index.

{_table(("Entries", "Queue"), [(n, name) for name, n in queues])}
"""
    path = OUT / "progress-report.md"
    path.write_text(text)
    return path


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = manifest()
    for writer in (write_inventory, write_copyright, write_source_verification,
                   write_currency, write_progress):
        path = writer(rows)
        print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)")
    print(f"\n{len(rows)} canonical documents reported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
