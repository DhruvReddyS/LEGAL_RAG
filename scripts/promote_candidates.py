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
SOURCES = ROOT / "data/source_materials"
MANIFEST = LIB / "metadata/canonical_documents.jsonl"
STAGING = LIB / "metadata/canonical_documents.staged.jsonl"
QUARANTINE = LIB / "metadata/quarantine.jsonl"
DUPLICATES = LIB / "metadata/duplicates.jsonl"
NEEDS_TITLE = LIB / "metadata/needs_title.jsonl"
OVERRIDES = LIB / "metadata/title_overrides.json"

# Documents whose subject is another state's subordinate rules dilute an
# Andhra-Pradesh-facing corpus and compete for the same ranking slots. They are
# quarantined rather than discarded: a later Kerala deployment would want them.
OTHER_STATE = re.compile(r"\bkerala|cochin|malabar\b", re.I)
# A second copy of an Act already indexed produces near-duplicate passages that
# crowd the four display slots without adding law.
ALREADY_INDEXED = re.compile(r"^(final_bns|final_bnss|final_bsa|the constitution of india)", re.I)

CATEGORY = [
    (re.compile(r"__rbi__", re.I), "primary_law/banking_finance"),
    (re.compile(r"__irdai?__", re.I), "primary_law/insurance"),
    (re.compile(r"__sebi__", re.I), "primary_law/securities_markets"),
    (re.compile(r"__incometax__", re.I), "primary_law/taxation"),
    (re.compile(r"__moefcc__", re.I), "primary_law/environment"),
    (re.compile(r"__mohfw__", re.I), "primary_law/health_medical"),
    (re.compile(r"__moe__", re.I), "primary_law/education"),
    (re.compile(r"right to information|\brti\b|__cic__", re.I),
     "primary_law/transparency_rti"),
    (re.compile(r"__ncpcr__", re.I), "official_guidance/child_protection"),
    (re.compile(r"__nhrc__", re.I), "official_guidance/human_rights"),
    (re.compile(r"reserve bank|\brbi\b|master direction|banking regulation|"
                r"payment (and settlement|aggregator|system)|prepaid payment|"
                r"negotiable instrument|\bnpa\b|priority sector", re.I),
     "primary_law/banking_finance"),
    (re.compile(r"\birdai?\b|insurance regulatory|life insurance|general insurance|"
                r"policyholder", re.I),
     "primary_law/insurance"),
    (re.compile(r"\bsebi\b|securities (and exchange|contracts)|listing obligations|"
                r"mutual fund|insider trading", re.I),
     "primary_law/securities_markets"),
    (re.compile(r"income.tax|\bgst\b|central excise|customs act|finance act|"
                r"direct tax|tax deducted", re.I),
     "primary_law/taxation"),
    (re.compile(r"environment \(protection\)|forest conservation|wildlife protection|"
                r"air \(prevention|water \(prevention|pollution control|"
                r"biological diversity|coastal regulation|green tribunal", re.I),
     "primary_law/environment"),
    (re.compile(r"clinical establishment|drugs and cosmetics|mental healthcare|"
                r"transplantation of human organ|national medical commission|"
                r"epidemic diseases|food safety", re.I),
     "primary_law/health_medical"),
    (re.compile(r"right of children to free and compulsory|university grants|"
                r"national education policy|anti.ragging|\bncte\b|\baicte\b", re.I),
     "primary_law/education"),
    # Protective legislation for women and children is asked about as its own
    # body of law - who may complain, to whom, within what time - so it gets
    # its own slot rather than sitting under family law or general crime.
    (re.compile(r"sexual-offences|child-rights|posh|sexual-harassment|dowry|sati|"
                r"indecent-representation|immoral-traffic|child-marriage|juvenile|"
                r"adoption|orphanages|infant-milk|national-commission-for-women", re.I),
     "primary_law/women_children"),
    (re.compile(r"termination-of-pregnancy|surrogacy|pcpndt|hiv-aids|maternity", re.I),
     "primary_law/health_reproductive"),
    (re.compile(r"disabilities", re.I), "primary_law/disability_welfare"),
    (re.compile(r"human rights advisory|advisory .*(human rights|welfare|rehabilitat)|"
                r"protection of human rights|bonded labour|leprosy|widows", re.I),
     "official_guidance/human_rights"),
    (re.compile(r"scheduled castes|scheduled tribes|atrocities|civil rights|"
                r"transgender|older persons|senior citizens|untouchability|"
                r"alcoholism|substance abuse|marginalised", re.I),
     "primary_law/social_justice"),
    (re.compile(r"code-on-wages|social-security|occupational-safety|industrial-relations", re.I),
     "primary_law/labour_welfare"),
    (re.compile(r"__constitution__|__amendment__constitution-|__sor__", re.I),
     "primary_law/constitution"),
    (re.compile(r"consumer|bureau-of-indian-standards|ncdrc", re.I),
     "primary_law/consumer_protection"),
    (re.compile(r"nalsa|lok-adalat|legal-services|legal-aid|para-legal|sahayata|yojana|shiksha|spruha|jagriti|samvad|dawn", re.I),
     "official_guidance/legal_aid"),
    (re.compile(r"rules-of-practice|case-flow|e-filing|electronic-processes|appellate-side|writ-rules|commercial-courts", re.I),
     "primary_law/civil_procedure"),
    (re.compile(r"high-court-manual|live-streaming|video-conferencing|court-recording|hearings-sop|judicial-manual", re.I),
     "official_guidance/police_courts"),
    (re.compile(r"pre-arrest|in-custody|utrc|premature-release|prison-legal-aid|juvenile|sexual-offences|community-mediation", re.I),
     "official_guidance/prisons_bail"),
    (re.compile(r"marriage|succession|divorce|guardian|domestic-violence|child-marriage|family-courts|shariat|muslim-women|senior-citizens|juvenile", re.I),
     "primary_law/family_personal_law"),
    # Word boundaries only. Narrowing this to phrases like "stamp act" was
    # tried and moved six real documents out, because a filename-derived title
    # reads "Stamp 1899", not "The Indian Stamp Act, 1899". The regulators that
    # used to collide here - a circular on registration of insurers - are
    # matched by their publisher token further up, before this rule is reached.
    (re.compile(r"\btransfer of property\b|transfer-property|\bregistration\b|"
                r"\bstamp\b|\bland\b|\bendowment|\bpanchayat|\bexcise\b", re.I),
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

# Some ministries serve content-hashed filenames, so the name carries no title
# at all. The document's own first page does. A filename ending in __xx says
# acquisition could not read a title and promotion must.
OPAQUE = re.compile(r"__xx\.pdf$|^[0-9a-f]{24,}\.pdf$", re.I)

# Boilerplate that sits above the real title on a gazette page.
_MASTHEAD = re.compile(
    r"^(the gazette of india|extraordinary|part [ivx]+|section \d|published by|"
    r"registered no|government of india|ministry of|no\.\s|new delhi|"
    r"\u092d\u093e\u0930\u0924|\u0930\u093e\u091c\u092a\u0924\u094d\u0930)", re.I)
_TITLE_CUE = re.compile(r"\b(act|rules|regulations|notification|amendment|order|scheme|bill|code)\b", re.I)

# A short title as a statute prints it: "The ... Act, 2025", "... Rules, 2021".
# This is what a citation names, so it is preferred over any other line.
_SHORT_TITLE = re.compile(
    r"^(?:the\s+)?[A-Z(][^.]{8,120}?\s(?:Act|Rules|Regulations|Sanhita|Adhiniyam|"
    r"Code|Scheme|Order|Bill|Guidelines|Manual|Memorandum)(?:,|\s)\s*\d{4}\b[^.]{0,40}$",
    re.I)

def suggest_title(doc) -> str | None:
    """A guess at the title from the document's opening pages.

    This is a suggestion for a reviewer, never a title. Gazette pages name
    other statutes as often as their own, so an automatic reading picks the
    wrong short title often enough that no citation should rest on it.

    Gazette pages carry a bilingual masthead above the operative text, and
    several ministries publish Hindi first, so the English short title can be
    pages in. Searching the opening pages rather than the first finds it.
    """
    lines: list[str] = []
    for index in range(min(len(doc), 4)):
        for line in doc[index].get_text("text").splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            if len(line) > 12 and not _MASTHEAD.match(line):
                lines.append(line)
    for line in lines:
        if _SHORT_TITLE.match(line):
            return line.strip(" .,:;-\u2014")
    cued = [line for line in lines if _TITLE_CUE.search(line)]
    for line in cued or lines:
        if 12 < len(line) <= 160:
            return line.strip(" .,:;-\u2014")
    return None


_SCRIPTS = {
    "devanagari": (0x0900, 0x097F),
    "telugu": (0x0C00, 0x0C7F),
}

def dominant_script(text: str) -> str:
    """Which script the text is written in: 'latin', a named Indic script, or 'none'."""
    counts = {"latin": 0} | {name: 0 for name in _SCRIPTS}
    for char in text:
        if char.isalpha():
            if char.isascii():
                counts["latin"] += 1
                continue
            point = ord(char)
            for name, (low, high) in _SCRIPTS.items():
                if low <= point <= high:
                    counts[name] += 1
                    break
    total = sum(counts.values())
    if total < 200:
        return "none"
    name, count = max(counts.items(), key=lambda pair: pair[1])
    return name if count / total > 0.5 else "none"


def source_records() -> dict[str, dict]:
    """What acquisition already knew about each file, keyed by filename.

    The source manifests carry a title, a publisher and a currency note that
    were checked against the page the link came from. Re-deriving any of that
    from the filename throws away the better evidence.
    """
    records: dict[str, dict] = {}
    for manifest in sorted(SOURCES.glob("*.json")):
        try:
            rows = json.loads(manifest.read_text())
        except json.JSONDecodeError:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("filename"):
                records[row["filename"]] = row | {"_manifest": manifest.name}
    return records


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def title_from(name: str) -> str:
    stem = re.sub(r"\.pdf$", "", name, flags=re.I)
    stem = re.sub(r"^(central|ap|ts)__[a-z-]+__[a-z-]+__", "", stem)
    stem = stem.replace("__", " ").replace("-", " ").replace("_", " ")
    stem = re.sub(r"\s+en$", "", stem).strip()
    return re.sub(r"\s+", " ", stem).title()

SOURCE_TYPES = [
    (re.compile(r"__constitution__", re.I), "act"),
    (re.compile(r"__sor__", re.I), "official_guidance"),
    (re.compile(r"__(rules|regulations|amendment|notification)__", re.I), "rule"),
    (re.compile(r"__(guidance|manual|handbook|compendium|scheme)__", re.I), "official_guidance"),
    (re.compile(r"__act__", re.I), "act"),
    (re.compile(r"rules?|regulation|notification", re.I), "rule"),
    (re.compile(r"guidance|manual|booklet|comparison|scheme|sop", re.I), "official_guidance"),
]

def source_type(path: Path) -> str:
    for pattern, kind in SOURCE_TYPES:
        if pattern.search(path.name):
            return kind
    return "act"

def classify(path: Path, title: str | None = None) -> str:
    subject = f"{title or ''} {path.name}"
    for pattern, category in CATEGORY:
        if pattern.search(subject):
            return category
    return "primary_law/other_relevant_laws"

# The publisher token in the filename, which is more reliable than guessing
# the authority from the subject matter.
PUBLISHERS = {
    "aphc": ("India - Andhra Pradesh", "High Court of Andhra Pradesh"),
    "tshc": ("India - Telangana", "High Court for the State of Telangana"),
    "nalsa": ("India - Central", "National Legal Services Authority"),
    "legislative": ("India - Central", "Legislative Department, Ministry of Law and Justice"),
    "ncdrc": ("India - Central", "National Consumer Disputes Redressal Commission"),
    "meity": ("India - Central", "Ministry of Electronics and Information Technology"),
    "wcd": ("India - Central", "Ministry of Women and Child Development"),
    "ncpcr": ("India - Central", "National Commission for Protection of Child Rights"),
    "nhrc": ("India - Central", "National Human Rights Commission"),
    "cic": ("India - Central", "Central Information Commission"),
    "socialjustice": ("India - Central", "Department of Social Justice and Empowerment"),
}

def _publisher_token(name: str) -> str | None:
    parts = name.split("__")
    return parts[1] if len(parts) > 2 else None

def jurisdiction(path: Path) -> str:
    known = PUBLISHERS.get(_publisher_token(path.name) or "")
    if known:
        return known[0]
    if re.search(r"^ap-|aphc|andhra", path.name, re.I) or path.name.startswith("ap__"):
        return "India - Andhra Pradesh"
    if path.name.startswith("ts__") or re.search(r"telangana", path.name, re.I):
        return "India - Telangana"
    return "India - Central"

def authority(path: Path) -> str:
    known = PUBLISHERS.get(_publisher_token(path.name) or "")
    if known:
        return known[1]
    place = jurisdiction(path)
    if place == "India - Central":
        return "Government of India"
    return f"Government of {place.split(' - ')[1]}"

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
    # A checksum already in the manifest means the same bytes arrived by a
    # second route - two publishers hosting one Act. Recording it is the point:
    # it is evidence that acquisition is converging, not a silent skip.
    by_checksum = {}
    for line in MANIFEST.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            by_checksum[row["sha256"]] = row.get("title") or row.get("original_filename")

    overrides = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    acquired = source_records()
    promoted, held, duplicates, untitled = [], [], [], []
    for path in sorted(CAND.rglob("*.pdf")):
        checksum = sha256(path)
        if checksum in have:
            duplicates.append({"file": path.name, "sha256": checksum,
                               "same_bytes_as": by_checksum.get(checksum),
                               "seen_at": datetime.now(timezone.utc).isoformat()})
            continue
        record = {"file": path.name, "batch": path.relative_to(CAND).parts[0], "sha256": checksum}
        # Validation: it must open, and it must yield text or be flagged for OCR.
        try:
            with fitz.open(path) as doc:
                pages = len(doc)
                chars = sum(len(doc[i].get_text("text")) for i in range(min(pages, 12)))
                # The script decision reads every page. A bilingual gazette
                # prints Hindi first and English after, so a sample of the
                # opening pages calls an English document Devanagari-only.
                sample = "".join(page.get_text("text") for page in doc)
                suggested = suggest_title(doc) if pages else None
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
        # BGE-M3 would embed Devanagari happily, but reasoning, verification
        # and generation all run in English, so a Hindi-only copy of an Act we
        # hold in English only crowds the ranking. Held, not discarded: a Hindi
        # deployment would want it, and so would a bilingual answer path.
        script = dominant_script(sample)
        if script in _SCRIPTS:
            held.append(record | {"reason": f"{script.title()}-only text; this corpus answers in English",
                                  "page_count": pages}); continue
        if re.match(r"^\d{10,}_", path.name):
            held.append(record | {"reason": "unidentified scan; needs a title and source before promotion"}); continue

        # A content-hashed filename carries no title, and reading one off the
        # page is unreliable. Such a document waits in a queue with its
        # suggestion until a reviewer records a title in title_overrides.json.
        acquisition = acquired.get(path.name) or {}
        if acquisition.get("title"):
            name = acquisition["title"]
        elif path.name in overrides:
            name = overrides[path.name]
        elif OPAQUE.search(path.name):
            untitled.append(record | {"suggested_title": suggested, "page_count": pages,
                                      "reason": "filename carries no title; record one in title_overrides.json"})
            continue
        else:
            name = title_from(path.name)
        category = classify(path, name)
        promoted.append({
            "document_id": f"exp-doc-{uuid.uuid4().hex[:24]}",
            "canonical_document_id": f"exp-canonical-{checksum[:24]}",
            "source_id": re.sub(r"\.pdf$", "", path.name, flags=re.I)[:80],
            "title": name,
            "act_name": name,
            "original_filename": path.name,
            "local_path": "",  # set when copied
            "source_type": source_type(path),
            "currency_note": acquisition.get("currency_note"),
            "source_url": acquisition.get("url"),
            "category": category,
            "authority": acquisition.get("authority") or authority(path),
            "jurisdiction": acquisition.get("jurisdiction") or jurisdiction(path),
            "language": (acquisition.get("language") if acquisition.get("language") not in (None, "unknown")
                         else ("Telugu" if re.search(r"telugu", path.name, re.I) else "English")),
            "year": int(m.group(0)) if (m := re.search(r"(18|19|20)\d{2}", path.name)) else None,
            # A reviewer who titled a document "(superseded)" has already made
            # the currency finding; the manifest must carry it, or retrieval
            # will offer an old consolidation as the law in force.
            "current_status": "superseded" if re.search(r"supersed|repealed", name, re.I) else "current/verify",
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
    DUPLICATES.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in duplicates), encoding="utf-8")
    NEEDS_TITLE.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in untitled), encoding="utf-8")

    import collections
    print(f"promoted {len(promoted)} documents, {sum(e['page_count'] for e in promoted)} pages")
    for cat, n in collections.Counter(e["category"] for e in promoted).most_common():
        print(f"   {n:3}  {cat}")
    if duplicates:
        print(f"\n{len(duplicates)} already held under another name:")
        for entry in duplicates[:6]:
            print(f"   {entry['file'][:46]}  ==  {str(entry['same_bytes_as'])[:40]}")
    if untitled:
        print(f"\n{len(untitled)} waiting for a title -> {NEEDS_TITLE.relative_to(ROOT)}")
    print(f"\nquarantined {len(held)}")
    for reason, n in collections.Counter(e["reason"][:60] for e in held).most_common():
        print(f"   {n:3}  {reason}")
    ocr = [e for e in promoted if e["ocr_required"]]
    if ocr: print(f"\nOCR queue: {len(ocr)} -> " + ", ".join(e["original_filename"][:34] for e in ocr[:5]))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
