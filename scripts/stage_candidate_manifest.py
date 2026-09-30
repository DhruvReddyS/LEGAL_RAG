#!/usr/bin/env python3
"""Turn acquired candidate documents into canonical manifest entries.

Acquisition downloads files and records where they came from. Ingestion reads
`canonical_documents.jsonl`. Nothing joined the two, so sixteen documents
downloaded on 11 September -- consumer protection, tenancy and real estate,
civil procedure, limitation, negotiable instruments, motor vehicles -- sat in
the candidate folder and never reached the index.

Entries are written to a separate file, not merged. Merging is a deliberate
act, and must not happen while a rebuild is running: the supervisor fixes its
target when it starts, and the pipeline re-reads the manifest on every attempt.

    python scripts/stage_candidate_manifest.py            # write the staging file
    python scripts/stage_candidate_manifest.py --merge    # append into the manifest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

REGISTRY = ROOT / "data" / "source_materials" / "phase_a_official_sources.json"
CANDIDATES = ROOT / "data" / "source_materials" / "candidate_imports" / "citizen_law_phase_a"
MANIFEST = ROOT / "data" / "legal_kb" / "metadata" / "canonical_documents.jsonl"
STAGING = ROOT / "data" / "legal_kb" / "metadata" / "canonical_documents.staged.jsonl"
LIBRARY = ROOT / "data" / "legal_kb"

# Where each domain's documents belong in the library, following the folders
# the existing manifest already uses.
DOMAIN_CATEGORY = {
    "consumer_ecommerce": "primary_law/other_relevant_laws",
    "ap_tenancy_property_rera": "primary_law/other_relevant_laws",
    "civil_procedure_legal_aid": "primary_law/other_relevant_laws",
    "banking_payments_cheques": "primary_law/other_relevant_laws",
    "motor_vehicle_accidents": "primary_law/other_relevant_laws",
}
TYPE_CATEGORY = {
    "rule": "rules_amendments_notifications",
    "guidelines": "rules_amendments_notifications",
    "corrigendum": "rules_amendments_notifications",
    "advisory": "official_guidance",
    "guidance": "official_guidance",
    "faq": "official_guidance",
    "portal": "official_guidance",
}


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def page_count(path: Path) -> int:
    import pymupdf as fitz

    with fitz.open(path) as document:
        return len(document)


def build_entry(source: dict, path: Path, existing: set[str]) -> dict | None:
    checksum = digest(path)
    if checksum in existing:
        print(f"  skip (already in the manifest by checksum): {path.name}")
        return None
    document_type = str(source.get("document_type") or "act").lower()
    category = TYPE_CATEGORY.get(document_type) or DOMAIN_CATEGORY.get(
        str(source.get("domain")), "primary_law/other_relevant_laws"
    )
    return {
        "document_id": f"phasea-doc-{uuid.uuid4().hex[:24]}",
        "canonical_document_id": f"phasea-canonical-{checksum[:24]}",
        "source_id": str(source["id"]),
        "title": str(source["title"]),
        "original_filename": path.name,
        "local_path": str(Path(category) / path.name),
        "source_type": document_type if document_type in {"act", "rule", "advisory"} else "official_guidance",
        "category": category,
        "authority": source.get("authority"),
        "jurisdiction": source.get("jurisdiction"),
        "act_name": str(source["title"]),
        "year": int(str(source.get("title", ""))[-5:-1]) if str(source.get("title", ""))[-5:-1].isdigit() else None,
        # Carried from the registry rather than asserted here. These sources
        # were acquired for review and none has been checked against the
        # Gazette, so nothing claims to be current.
        "current_status": str(source.get("legal_status") or "STATUS_REQUIRES_REVIEW"),
        "language": str(source.get("language") or "English"),
        "source_url": source.get("url"),
        "sha256": checksum,
        "file_size": path.stat().st_size,
        "page_count": page_count(path),
        "verified_official": bool(source.get("authority")),
        "quality_status": "candidate_review",
        "notes": source.get("currency_note"),
        "acquired_at": source.get("current_as_of"),
        "staged_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merge", action="store_true", help="append staged entries into the manifest")
    arguments = parser.parse_args()

    if arguments.merge:
        if not STAGING.is_file():
            print("nothing staged; run without --merge first")
            return 1
        staged = [json.loads(line) for line in STAGING.read_text().splitlines() if line.strip()]
        existing = {json.loads(line)["sha256"] for line in MANIFEST.read_text().splitlines() if line.strip()}
        fresh = [entry for entry in staged if entry["sha256"] not in existing]
        missing = [entry for entry in fresh if not (LIBRARY / entry["local_path"]).is_file()]
        if missing:
            print("refusing to merge: these entries have no file in the library")
            for entry in missing:
                print(f"  {entry['local_path']}")
            return 1
        with MANIFEST.open("a", encoding="utf-8") as handle:
            for entry in fresh:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        print(f"merged {len(fresh)} entries into {MANIFEST.relative_to(ROOT)}")
        return 0

    registry = {str(item["id"]): item for item in json.loads(REGISTRY.read_text())}
    existing = {json.loads(line)["sha256"] for line in MANIFEST.read_text().splitlines() if line.strip()}
    entries = []
    for path in sorted(CANDIDATES.rglob("*.pdf")):
        source = next((item for item in registry.values() if item.get("filename") == path.name), None)
        if source is None:
            print(f"  skip (not in the registry): {path.name}")
            continue
        entry = build_entry(source, path, existing)
        if entry is not None:
            entries.append(entry)

    STAGING.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in entries), encoding="utf-8")
    print(f"\nstaged {len(entries)} entries in {STAGING.relative_to(ROOT)}")
    print(f"total pages: {sum(e['page_count'] for e in entries)}")
    print("\nnext, once no rebuild is running:")
    print("  1. copy each file to data/legal_kb/<category>/")
    print("  2. python scripts/stage_candidate_manifest.py --merge")
    print("  3. resume ingestion; the pipeline skips documents already checkpointed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
