#!/usr/bin/env python3
"""Copy and freeze LEGAL_KB_V1_GOLD from its verified source manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_ROOT = REPOSITORY_ROOT / "data" / "legal_kb"
VERSION_NAME = "LEGAL_KB_V1_GOLD"
VERSION_DATE = "2026-08-20"
EXPECTED_RECORD_COUNT = 419

DIRECTORIES = (
    "raw/primary_law/constitution",
    "raw/primary_law/bns",
    "raw/primary_law/bnss",
    "raw/primary_law/bsa",
    "raw/primary_law/legacy_ipc_crpc_evidence",
    "raw/primary_law/special_criminal_laws",
    "raw/primary_law/other_relevant_laws",
    "raw/rules_amendments_notifications",
    "raw/judgments/supreme_court",
    "raw/judgments/high_court/telangana",
    "raw/judgments/high_court/andhra_pradesh",
    "raw/judgments/high_court/delhi",
    "raw/judgments/high_court/bombay",
    "raw/judgments/high_court/karnataka",
    "raw/judgments/high_court/other",
    "raw/official_guidance/mha",
    "raw/official_guidance/bprd",
    "raw/official_guidance/ncrb",
    "raw/official_guidance/police_investigation",
    "raw/official_guidance/prisons_bail",
    "raw/official_guidance/digital_evidence",
    "raw/government_handbooks",
    "raw/law_commission_reports",
    "raw/legal_forms_templates",
    "raw/secondary_open_reference",
    "metadata/source_manifests",
    "mapping",
    "processed/extracted_text",
    "processed/normalized",
    "processed/chunks",
    "cache/embeddings",
    "logs",
)

SPECIAL_LAW_TERMS = (
    "arms act",
    "atrocities",
    "corruption",
    "dowry",
    "domestic violence",
    "juvenile justice",
    "legal services authorities",
    "narcotic",
    "ndps",
    "national security act",
    "pocso",
    "protection of children",
    "scheduled castes",
    "scheduled tribes",
    "unlawful activities",
)


def classify(record: dict[str, Any]) -> str:
    source_type = str(record.get("source_type", "")).lower()
    title = str(record.get("title", "")).lower()
    authority = str(record.get("authority", "")).lower()
    court = str(record.get("court", "")).lower()
    combined = " ".join((title, authority, str(record.get("notes", "")).lower()))

    if source_type == "judgment":
        if "supreme court" in court:
            return "judgments/supreme_court"
        if "telangana" in court:
            return "judgments/high_court/telangana"
        if "andhra pradesh" in court:
            return "judgments/high_court/andhra_pradesh"
        if "delhi" in court:
            return "judgments/high_court/delhi"
        if "bombay" in court or "mumbai" in court:
            return "judgments/high_court/bombay"
        if "karnataka" in court:
            return "judgments/high_court/karnataka"
        return "judgments/high_court/other"

    if source_type == "constitution" or "constitution of india" in title:
        return "primary_law/constitution"
    if source_type in {"rule", "amendment_act", "notification", "order"}:
        return "rules_amendments_notifications"
    if source_type == "law_commission_report" or "law commission" in authority:
        return "law_commission_reports"
    if source_type in {"handbook", "manual", "training_module"}:
        return "government_handbooks"
    if "form" in title and source_type == "official_legal_material":
        return "legal_forms_templates"

    if source_type == "act":
        if "bharatiya nyaya sanhita" in title:
            return "primary_law/bns"
        if "bharatiya nagarik suraksha sanhita" in title:
            return "primary_law/bnss"
        if "bharatiya sakshya adhiniyam" in title:
            return "primary_law/bsa"
        if any(term in title for term in ("indian penal code", "criminal procedure", "evidence act")):
            return "primary_law/legacy_ipc_crpc_evidence"
        if any(term in title for term in SPECIAL_LAW_TERMS):
            return "primary_law/special_criminal_laws"
        return "primary_law/other_relevant_laws"

    if "bureau of police research" in authority or "bpr&d" in combined or "bprd" in combined:
        return "official_guidance/bprd"
    if "ncrb" in combined or "crime records bureau" in combined:
        return "official_guidance/ncrb"
    if any(term in combined for term in ("digital evidence", "electronic evidence", "cyber")):
        return "official_guidance/digital_evidence"
    if any(term in combined for term in ("prison", "bail", "undertrial")):
        return "official_guidance/prisons_bail"
    if source_type == "sop" or any(term in combined for term in ("investigation", "police", "prosecution")):
        return "official_guidance/police_investigation"
    return "official_guidance/mha"


def page_count(path: Path) -> int | None:
    result = subprocess.run(
        ["pdfinfo", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def derive_case_number(title: str) -> str | None:
    patterns = (
        r"\b(?:Crl\.?A\.?|C\.?A\.?|W\.?P\.?(?:\(Crl\.?\)|\(C\))?|SLP\s*\([^)]*\)|SMW\([^)]*\)|R\.?P\.?(?:\(Crl\.\))?)\s+No\.\s*[^\n]+$",
        r"\b(?:Criminal|Civil) Appeal No\.\s*[^\n]+$",
    )
    for pattern in patterns:
        match = re.search(pattern, title, flags=re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def decision_year(record: dict[str, Any]) -> int | None:
    date = str(record.get("document_date", ""))
    match = re.search(r"\b(19|20)\d{2}\b", date)
    if match:
        return int(match.group(0))
    if str(record.get("source_type", "")) == "judgment":
        filename_match = re.search(r"_(20\d{2})-\d{2}-\d{2}", str(record.get("original_filename", "")))
        if filename_match:
            return int(filename_match.group(1))
    return None


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a verified source corpus, then copy and freeze it as "
            f"{VERSION_NAME}."
        )
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help=(
            "Verified source-corpus directory containing manifests/documents.jsonl "
            "and manifests/corpus_summary.json."
        ),
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=DEFAULT_TARGET_ROOT,
        help=(
            "Gold corpus destination (default: repository data/legal_kb). "
            "Existing matching PDFs are preserved; generated metadata is refreshed."
        ),
    )
    return parser


def validate_roots(source_root: Path, target_root: Path) -> tuple[Path, Path]:
    source_root = source_root.expanduser().resolve()
    target_root = target_root.expanduser().resolve()

    if not source_root.is_dir():
        raise ValueError(f"source root is not a directory: {source_root}")
    for relative_path in (
        Path("manifests/documents.jsonl"),
        Path("manifests/corpus_summary.json"),
    ):
        if not (source_root / relative_path).is_file():
            raise ValueError(f"source root is missing {relative_path}: {source_root}")
    if target_root.exists() and not target_root.is_dir():
        raise ValueError(f"target root exists but is not a directory: {target_root}")
    if (
        target_root == source_root
        or source_root in target_root.parents
        or target_root in source_root.parents
    ):
        raise ValueError("source and target roots must not overlap")

    return source_root, target_root


def organize(source_root: Path, target_root: Path) -> None:
    manifest_path = source_root / "manifests/documents.jsonl"
    records = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    if len(records) != EXPECTED_RECORD_COUNT:
        raise RuntimeError(
            f"Expected {EXPECTED_RECORD_COUNT} manifest records, found {len(records)}"
        )

    for directory in DIRECTORIES:
        (target_root / directory).mkdir(parents=True, exist_ok=True)

    source_urls_by_sha: dict[str, set[str]] = defaultdict(set)
    counts_by_sha = Counter(str(record["sha256"]) for record in records)
    for record in records:
        if record.get("source_url"):
            source_urls_by_sha[str(record["sha256"])].add(str(record["source_url"]))
        if record.get("item_url"):
            source_urls_by_sha[str(record["sha256"])].add(str(record["item_url"]))

    canonical_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, str]] = []
    category_counts: Counter[str] = Counter()
    page_count_failures: list[str] = []
    copied = 0
    total_bytes = 0

    for record in records:
        source_path = source_root / str(record["local_path"])
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        actual_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
        expected_sha = str(record["sha256"])
        if actual_sha != expected_sha:
            raise RuntimeError(f"SHA-256 mismatch: {source_path}")

        category = classify(record)
        document_id = "gold-doc-" + hashlib.sha256(
            f"{record['record_id']}|{record['local_path']}".encode()
        ).hexdigest()[:24]
        canonical_id = "gold-canonical-" + expected_sha[:24]
        destination = target_root / "raw" / category / document_id / source_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).hexdigest() != expected_sha:
                raise RuntimeError(f"Existing target differs: {destination}")
        else:
            shutil.copy2(source_path, destination)
            copied += 1

        pages = page_count(destination)
        if pages is None:
            page_count_failures.append(str(destination.relative_to(target_root)))
        file_size = destination.stat().st_size
        total_bytes += file_size
        category_counts[category] += 1
        relative_path = str(destination.relative_to(target_root))
        source_type = str(record.get("source_type", ""))
        date = normalize_date(str(record.get("document_date", "")) or None)
        year_value = str(record.get("year", ""))
        row = {
            "document_id": document_id,
            "canonical_document_id": canonical_id,
            "source_id": record.get("record_id"),
            "title": record.get("title") or source_path.stem,
            "original_filename": record.get("original_filename") or source_path.name,
            "local_path": relative_path,
            "source_type": source_type,
            "category": category,
            "authority": record.get("authority") or None,
            "jurisdiction": record.get("jurisdiction") or None,
            "court": record.get("court") or None,
            "case_title": record.get("title") if source_type == "judgment" else None,
            "case_number": derive_case_number(str(record.get("title", ""))) if source_type == "judgment" else None,
            "neutral_citation": None,
            "decision_date": date if source_type == "judgment" else None,
            "decision_year": decision_year(record),
            "act_name": record.get("parent_act") or (record.get("title") if source_type in {"act", "constitution"} else None),
            "section": record.get("act_section") or None,
            "year": int(year_value) if year_value.isdigit() else None,
            "effective_from": normalize_date(str(record.get("effective_date", "")) or None),
            "effective_to": None,
            "current_status": record.get("legal_status") or "current/verify",
            "supersedes": None,
            "superseded_by": None,
            "language": record.get("language") or "English",
            "source_url": record.get("source_url") or None,
            "alternate_source_urls": sorted(source_urls_by_sha[expected_sha]),
            "sha256": expected_sha,
            "file_size": file_size,
            "page_count": pages,
            "verified_official": True,
            "duplicate_group": f"sha256:{expected_sha}" if counts_by_sha[expected_sha] > 1 else None,
            "quality_status": "verified",
            "notes": record.get("notes") or None,
        }
        canonical_rows.append(row)
        mapping_rows.append(
            {
                "document_id": document_id,
                "canonical_document_id": canonical_id,
                "source_local_path": str(record["local_path"]),
                "gold_local_path": relative_path,
            }
        )

    canonical_path = target_root / "metadata/canonical_documents.jsonl"
    canonical_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in canonical_rows)
    )
    mapping_path = target_root / "mapping/physical_to_canonical.jsonl"
    mapping_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in mapping_rows)
    )
    shutil.copytree(
        source_root / "manifests",
        target_root / "metadata/source_manifests",
        dirs_exist_ok=True,
    )
    (target_root / "VERSION").write_text(f"{VERSION_NAME}\n{VERSION_DATE}\n")

    summary = json.loads((source_root / "manifests/corpus_summary.json").read_text())
    readme = f"""# Legal Knowledge Base

Version: **{VERSION_NAME}**  
Freeze date: **{VERSION_DATE}**

## Gold corpus

- Physical PDFs: **{len(records)}**
- Total size: **{total_bytes:,} bytes ({total_bytes / 1024**3:.3f} GiB)**
- Courts: Supreme Court of India (99); High Court of Andhra Pradesh (16)
- Mandatory legislation coverage: **{summary['mandatory_items_present']} / {summary['mandatory_items_total']}**
- Known gap: Advocates Act, 1961 standalone bare Act PDF
- Exact duplicate-content groups: **{summary['duplicate_sha256_groups']}**

All PDFs were copied from the verified source corpus without changing their contents or
original filenames. Physical duplicates are intentionally retained. Rows sharing a SHA-256
share a `canonical_document_id`; downstream embedding must process only one row per canonical ID.

## Provenance and trust boundaries

The source manifest, official source URLs, download provenance, checksums, and alternate URLs
are retained under `metadata/`. The immutable verified set is the **Gold** corpus. Any future
KanoonGPT-derived material belongs to a separate **Extended** corpus and must never replace,
silently override, or weaken Gold sources. Police and advocate case uploads remain private and
are stored outside both public corpus layers.
"""
    (target_root / "README.md").write_text(readme)

    report_lines = [
        "# Gold Corpus Organization Report",
        "",
        f"- Version: `{VERSION_NAME}`",
        f"- Source records: {len(records)}",
        f"- Physical PDFs in Gold raw tree: {len(canonical_rows)}",
        f"- Newly copied during this run: {copied}",
        f"- Canonical content objects: {len(counts_by_sha)}",
        f"- Duplicate-content groups: {sum(1 for count in counts_by_sha.values() if count > 1)}",
        f"- Total bytes: {total_bytes}",
        f"- Page-count failures: {len(page_count_failures)}",
        "",
        "## Classification counts",
        "",
    ]
    report_lines.extend(f"- `{category}`: {count}" for category, count in sorted(category_counts.items()))
    report_lines.extend(["", "## Classification and metadata issues", ""])
    if page_count_failures:
        report_lines.append("PDF page count could not be read for:")
        report_lines.extend(f"- `{path}`" for path in page_count_failures)
    else:
        report_lines.append("No integrity or page-count issues were found.")
    report_lines.extend(
        [
            "",
            "The source metadata does not consistently provide neutral citations, decision dates,",
            "sections, or supersession relationships. Unknown values remain null rather than being guessed.",
            "All records are official-source verified; legal status values marked `current/verify` remain",
            "explicitly flagged for later temporal validation.",
        ]
    )
    (target_root / "logs/organization_report.md").write_text("\n".join(report_lines) + "\n")

    print(
        json.dumps(
            {
                "physical_documents": len(canonical_rows),
                "canonical_documents": len(counts_by_sha),
                "copied": copied,
                "total_bytes": total_bytes,
                "page_count_failures": len(page_count_failures),
            },
            sort_keys=True,
        )
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        source_root, target_root = validate_roots(args.source_root, args.target_root)
    except ValueError as error:
        parser.error(str(error))
    organize(source_root, target_root)


if __name__ == "__main__":
    main()
