#!/usr/bin/env python3
"""Correct the manifest and add the Acts the corpus was missing.

Run once, between builds, never during one. Safe to run twice.

1. Adds the bare Acts listed in data/source_materials/missing_acts_2026-11-04.json.
   The corpus had no bare CrPC or Evidence Act, though retrieval, currency labels
   and the concordance all assume it did.
2. Files Law Commission reports as reports. 22 were typed `act` and titled like the
   Act they discuss, so "The Code of Criminal Procedure, 1973" was a 1996 report,
   counted as a bare Act by the coverage audit and labelled as the repealed Code.
3. Replaces the title "Download" on the NDPS Act and Rules.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "data" / "legal_kb"
MANIFEST = KB / "metadata" / "canonical_documents.jsonl"
BATCH = ROOT / "data" / "source_materials" / "missing_acts_2026-11-04.json"
CANDIDATES = ROOT / "data" / "source_materials" / "candidate_imports"
LAW_COMMISSION_HOST = "s3ca0daec69b5adc880fb464895726dbdf"
REPORT_PREFIX = "Law Commission of India report on "
SAVED_REPEALS = {"code-of-criminal-procedure-1973", "indian-evidence-act-1872"}
DOWNLOAD_TITLES = {
    "acts_files": "The Narcotic Drugs and Psychotropic Substances Act, 1985",
    "rules_files": "The Narcotic Drugs and Psychotropic Substances Rules, 1985",
}


def page_count(path: Path) -> tuple[int, int]:
    import pymupdf

    with pymupdf.open(path) as document:
        return len(document), sum(len(page.get_text()) for page in document)


def main() -> int:
    rows = [json.loads(line) for line in MANIFEST.open(encoding="utf-8")]
    held = {row.get("sha256") for row in rows}

    retyped = retitled = added = 0
    for row in rows:
        url = str(row.get("source_url") or "")
        if LAW_COMMISSION_HOST in url and row.get("source_type") == "act":
            row["source_type"] = "law_commission_report"
            if not str(row["title"]).startswith(REPORT_PREFIX):
                row["title"] = REPORT_PREFIX + str(row["title"])
            row["act_name"] = None
            retyped += 1
        if str(row.get("title")).strip().lower() == "download":
            for marker, title in DOWNLOAD_TITLES.items():
                if marker in url:
                    row["title"] = title
                    row["act_name"] = title
                    retitled += 1

    for source in json.loads(BATCH.read_text(encoding="utf-8")):
        path = CANDIDATES / source["filename"]
        if not path.is_file():
            print(f"not on disk, skipped: {source['title']} ({source['url']})")
            continue
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if checksum in held:
            continue
        pages, characters = page_count(path)
        document_id = f"exp-doc-{uuid.uuid4().hex[:24]}"
        relative = Path("raw") / "primary_law" / "other_relevant_laws" / document_id / path.name
        (KB / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, KB / relative)
        rows.append(
            {
                "act_name": source["title"],
                "authority": source["authority"],
                "canonical_document_id": f"exp-canonical-{checksum[:24]}",
                "category": "primary_law/other_relevant_laws",
                "copyright_status": "government work, free to use",
                "currency_note": source.get("currency_note"),
                "current_status": "superseded" if source["id"] in SAVED_REPEALS else "current/verify",
                "document_id": document_id,
                "file_size": path.stat().st_size,
                "jurisdiction": source["jurisdiction"],
                "language": "English",
                "licence": "Government of India / State official publication",
                "local_path": str(relative),
                "ocr_required": characters < pages * 100,
                "original_filename": path.name,
                "page_count": pages,
                "quality_status": "candidate_review",
                "retrieved_on": datetime.now(timezone.utc).date().isoformat(),
                "sha256": checksum,
                "source_id": path.stem[:80],
                "source_type": "act",
                "source_url": source["url"],
                "staged_at": datetime.now(timezone.utc).isoformat(),
                "title": source["title"],
                "verified_official": True,
                "year": int(source["title"].rsplit(" ", 1)[-1]),
            }
        )
        added += 1

    MANIFEST.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    print(f"added {added}, retyped {retyped} reports, retitled {retitled}, now {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
