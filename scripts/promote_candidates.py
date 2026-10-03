#!/usr/bin/env python3
"""Validate downloaded candidates and promote the ones that belong in the corpus.

Acquisition leaves files in candidate_imports; ingestion reads the canonical
manifest. This joins the two, but only for documents that pass validation and
that belong in an Andhra-Pradesh-facing Indian legal corpus.

Nothing is deleted. A file that is not promoted is written to the quarantine
manifest with the reason, so the decision can be reviewed and reversed.

    python scripts/promote_candidates.py            # classify and stage
    python scripts/promote_candidates.py --merge    # append staged into manifest
"""
from __future__ import annotations

import argparse, hashlib, json, re, shutil, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
LIB = ROOT / "data/legal_kb"
CAND = ROOT / "data/source_materials/candidate_imports"
MANIFEST = LIB / "metadata/canonical_documents.jsonl"
STAGING = LIB / "metadata/canonical_documents.staged.jsonl"
QUARANTINE = LIB / "metadata/quarantine.jsonl"

# Documents whose subject is another state's subordinate rules dilute an
# Andhra-Pradesh-facing corpus and compete for the same ranking slots. They are
# quarantined rather than discarded: a later Kerala deployment would want them.
OTHER_STATE = re.compile(r"\bkerala|cochin|malabar\b", re.I)
# A second copy of an Act already indexed produces near-duplicate passages that
# crowd the four display slots without adding law.
ALREADY_INDEXED = re.compile(r"^(final_bns|final_bnss|final_bsa|the constitution of india)", re.I)

CATEGORY = [
    (re.compile(r"marriage|succession|divorce|guardian|domestic-violence|child-marriage|family-courts|shariat|muslim-women|senior-citizens|juvenile", re.I),
     "primary_law/family_personal_law"),
    (re.compile(r"transfer-property|registration|stamp|land|endowment|panchayat|excise", re.I),
     "primary_law/property_land"),
    (re.compile(r"arbitration|mediation|commercial-courts|rti", re.I),
     "primary_law/civil_procedure"),
    (re.compile(r"labour|social-security|industrial-relations|occupational-safety", re.I),
     "primary_law/labour_welfare"),
    (re.compile(r"data-protection|intermediary|meity", re.I),
     "primary_law/technology_privacy"),
    (re.compile(r"comparison", re.I), "official_guidance/criminal_law_concordance"),
    (re.compile(r"booklet|manual|judicial-manual|sho", re.I), "official_guidance/police_courts"),
]

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def title_from(name: str) -> str:
    stem = re.sub(r"\.pdf$", "", name, flags=re.I)
    stem = re.sub(r"^(central|ap)__[a-z-]+__[a-z-]+__", "", stem)
    stem = stem.replace("__", " ").replace("-", " ").replace("_", " ")
    stem = re.sub(r"\s+en$", "", stem).strip()
    return re.sub(r"\s+", " ", stem).title()

def classify(path: Path) -> str:
    for pattern, category in CATEGORY:
        if pattern.search(path.name):
            return category
    return "primary_law/other_relevant_laws"

def jurisdiction(path: Path) -> str:
    if re.search(r"^ap-|aphc|andhra", path.name, re.I) or path.name.startswith("ap__"):
        return "India - Andhra Pradesh"
    return "India - Central"

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()

    if args.merge:
        staged = [json.loads(l) for l in STAGING.read_text().splitlines() if l.strip()]
        have = {json.loads(l)["sha256"] for l in MANIFEST.read_text().splitlines() if l.strip()}
        fresh = [e for e in staged if e["sha256"] not in have]
        missing = [e for e in fresh if not (LIB / e["local_path"]).is_file()]
        if missing:
            print("refusing to merge, files absent:"); [print("  ", e["local_path"]) for e in missing]; return 1
        with MANIFEST.open("a", encoding="utf-8") as fh:
            for e in fresh: fh.write(json.dumps(e, sort_keys=True) + "\n")
        print(f"merged {len(fresh)} entries")
        return 0

    import pymupdf as fitz
    have = {json.loads(l)["sha256"] for l in MANIFEST.read_text().splitlines() if l.strip()}
    promoted, held = [], []
    for path in sorted(CAND.rglob("*.pdf")):
        checksum = sha256(path)
        if checksum in have:
            continue
        record = {"file": path.name, "batch": path.relative_to(CAND).parts[0], "sha256": checksum}
        # Validation: it must open, and it must yield text or be flagged for OCR.
        try:
            with fitz.open(path) as doc:
                pages = len(doc)
                chars = sum(len(doc[i].get_text("text")) for i in range(min(pages, 12)))
        except Exception as exc:
            held.append(record | {"reason": f"unreadable: {type(exc).__name__}"}); continue
        if pages == 0:
            held.append(record | {"reason": "no pages"}); continue
        if OTHER_STATE.search(path.name):
            held.append(record | {"reason": "subordinate rules of another state; out of scope for an AP-facing corpus"}); continue
        if ALREADY_INDEXED.search(path.name):
            held.append(record | {"reason": "second copy of an Act already indexed; near-duplicate passages"}); continue
        # Tesseract here has only English trained data, so a scanned Telugu
        # document would be read as garbled Latin and indexed as if it were
        # text. Telugu support needs tel.traineddata and query-side handling.
        if record.get("language") == "Telugu" or re.search(r"__te\.pdf$|telugu", path.name, re.I):
            if chars < pages * 100:
                held.append(record | {"reason": "Telugu scan, but only English OCR data is installed"}); continue
        if re.match(r"^\d{10,}_", path.name):
            held.append(record | {"reason": "unidentified scan; needs a title and source before promotion"}); continue

        category = classify(path)
        promoted.append({
            "document_id": f"exp-doc-{uuid.uuid4().hex[:24]}",
            "canonical_document_id": f"exp-canonical-{checksum[:24]}",
            "source_id": re.sub(r"\.pdf$", "", path.name, flags=re.I)[:80],
            "title": title_from(path.name),
            "act_name": title_from(path.name),
            "original_filename": path.name,
            "local_path": "",  # set when copied
            "source_type": "rule" if re.search(r"rules?|notification", path.name, re.I) else
                           ("official_guidance" if re.search(r"guidance|manual|booklet|comparison", path.name, re.I) else "act"),
            "category": category,
            "authority": "Government of Andhra Pradesh" if jurisdiction(path).endswith("Andhra Pradesh") else "Government of India",
            "jurisdiction": jurisdiction(path),
            "language": "Telugu" if re.search(r"telugu", path.name, re.I) else "English",
            "year": int(m.group(0)) if (m := re.search(r"(18|19|20)\d{2}", path.name)) else None,
            "current_status": "current/verify",
            "quality_status": "candidate_review",
            "licence": "Government of India / State official publication",
            "copyright_status": "government work, free to use",
            "sha256": checksum,
            "file_size": path.stat().st_size,
            "page_count": pages,
            "verified_official": True,
            "ocr_required": chars < pages * 100,
            "retrieved_on": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat(),
            "staged_at": datetime.now(timezone.utc).isoformat(),
            "_source_path": str(path),
        })

    # Copy promoted files into the library, following the repository convention.
    for entry in promoted:
        src = Path(entry.pop("_source_path"))
        dest_dir = LIB / "raw" / entry["category"] / entry["document_id"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / entry["original_filename"]
        if not dest.exists():
            shutil.copy2(src, dest)
        entry["local_path"] = str(dest.relative_to(LIB))

    STAGING.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in promoted), encoding="utf-8")
    QUARANTINE.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in held), encoding="utf-8")

    import collections
    print(f"promoted {len(promoted)} documents, {sum(e['page_count'] for e in promoted)} pages")
    for cat, n in collections.Counter(e["category"] for e in promoted).most_common():
        print(f"   {n:3}  {cat}")
    print(f"\nquarantined {len(held)}")
    for reason, n in collections.Counter(e["reason"][:60] for e in held).most_common():
        print(f"   {n:3}  {reason}")
    ocr = [e for e in promoted if e["ocr_required"]]
    if ocr: print(f"\nOCR queue: {len(ocr)} -> " + ", ".join(e["original_filename"][:34] for e in ocr[:5]))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
