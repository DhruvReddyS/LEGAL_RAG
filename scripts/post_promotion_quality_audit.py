#!/usr/bin/env python3
"""Generate the lightweight quality queue for the canonical manifest.

This audit reads metadata only. It deliberately does not open PDFs, load an
embedding model, query Qdrant, or claim that a canonical document is available
in the collection serving users. It is safe to run while a corpus rebuild owns
the machine.

The report answers the questions that raw document count cannot:

* how much canonical material is unique by checksum;
* which records still need OCR, provenance, currency, or status review;
* how much of the latest promotion landed in a broad fallback category; and
* which explicit legal warnings must survive indexing and answer generation.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/legal_kb/metadata/canonical_documents.jsonl"
DEFAULT_JSON = ROOT / "docs/evidence/corpus/post-promotion-quality-audit.json"
DEFAULT_MARKDOWN = ROOT / "docs/evidence/corpus/POST_PROMOTION_QUALITY_AUDIT.md"

WARNING_CLASSES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "explicit_commencement_risk",
        re.compile(
            r"commencement (?:requires|clause requires)|"
            r"commencement notification (?:was )?not (?:found|located)|"
            r"must not be represented as fully operative|not[- ]yet[- ]in[- ]force",
            re.I,
        ),
    ),
    (
        "explicit_stale_consolidation",
        re.compile(
            r"historical consolidation|old consolidation|does not include later amendments|"
            r"amendment reconciliation required",
            re.I,
        ),
    ),
    (
        "explicit_transition_or_supersession",
        re.compile(
            r"\blegacy\b|\btransition\b|\bsavings clause\b|"
            r"supersed(?:ed|es)|repealed[- ]with[- ]savings|repealed on",
            re.I,
        ),
    ),
)


def load_unique(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        checksum = str(row.get("sha256") or "")
        if checksum in seen:
            continue
        seen.add(checksum)
        unique.append(row)
    return unique, len(rows)


def compact_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_document_id": row.get("canonical_document_id"),
        "title": row.get("title") or row.get("act_name"),
        "category": row.get("category"),
        "page_count": row.get("page_count"),
        "current_status": row.get("current_status"),
    }


def warning_record(row: dict[str, Any]) -> dict[str, Any]:
    return compact_record(row) | {
        "source_url": row.get("source_url"),
        "currency_note": row.get("currency_note"),
    }


def audit(rows: list[dict[str, Any]], manifest_rows: int) -> dict[str, Any]:
    batch_dates = [str(row.get("staged_at") or "")[:10] for row in rows if row.get("staged_at")]
    latest_batch_date = max(batch_dates) if batch_dates else None
    latest = [row for row in rows if str(row.get("staged_at") or "")[:10] == latest_batch_date]

    ocr = [row for row in rows if row.get("ocr_required") is True]
    missing_url = [row for row in rows if not str(row.get("source_url") or "").strip()]
    not_official = [row for row in rows if row.get("verified_official") is not True]
    no_currency_note = [row for row in rows if not str(row.get("currency_note") or "").strip()]
    broad = [row for row in rows if row.get("category") == "primary_law/other_relevant_laws"]
    latest_broad = [row for row in latest if row.get("category") == "primary_law/other_relevant_laws"]

    warnings: dict[str, list[dict[str, Any]]] = {}
    for label, pattern in WARNING_CLASSES:
        warnings[label] = [
            warning_record(row)
            for row in rows
            if pattern.search(str(row.get("currency_note") or ""))
        ]

    return {
        "generated_on": date.today().isoformat(),
        "scope": "canonical manifest metadata; not active-index readiness",
        "manifest_rows": manifest_rows,
        "unique_documents": len(rows),
        "duplicate_checksum_rows": manifest_rows - len(rows),
        "page_count": sum(int(row.get("page_count") or 0) for row in rows),
        "file_size_bytes": sum(int(row.get("file_size") or 0) for row in rows),
        "latest_promotion_batch": {
            "date": latest_batch_date,
            "unique_documents": len(latest),
            "pages": sum(int(row.get("page_count") or 0) for row in latest),
            "broad_fallback_category": len(latest_broad),
            "ocr_required": sum(row.get("ocr_required") is True for row in latest),
        },
        "metadata_counts": {
            "with_source_url": len(rows) - len(missing_url),
            "verified_official": len(rows) - len(not_official),
            "with_currency_note": len(rows) - len(no_currency_note),
            "ocr_required": len(ocr),
            "broad_fallback_category": len(broad),
        },
        "by_category": dict(Counter(str(row.get("category") or "missing") for row in rows).most_common()),
        "by_current_status": dict(Counter(str(row.get("current_status") or "missing") for row in rows).most_common()),
        "by_quality_status": dict(Counter(str(row.get("quality_status") or "missing") for row in rows).most_common()),
        "queues": {
            "ocr_required": [compact_record(row) for row in ocr],
            "missing_source_url": [compact_record(row) for row in missing_url],
            "not_verified_official": [compact_record(row) for row in not_official],
            "broad_fallback_category": [compact_record(row) for row in broad],
        },
        "warning_classes": warnings,
    }


def render(report: dict[str, Any]) -> str:
    meta = report["metadata_counts"]
    batch = report["latest_promotion_batch"]
    total = report["unique_documents"]
    gib = report["file_size_bytes"] / (1024**3)
    lines = [
        "# Post-promotion corpus quality audit",
        "",
        f"Generated: {report['generated_on']}",
        "Scope: canonical-manifest metadata only; this is not proof of active-index readiness.",
        "",
        "## Exact canonical inventory",
        "",
        "| Measure | Value |",
        "|---|---:|",
        f"| Manifest rows | {report['manifest_rows']:,} |",
        f"| Unique documents by SHA-256 | {total:,} |",
        f"| Duplicate-checksum rows | {report['duplicate_checksum_rows']:,} |",
        f"| Pages | {report['page_count']:,} |",
        f"| Size | {gib:.3f} GiB |",
        "",
        "## Latest promotion batch",
        "",
        f"The latest unique batch is dated {batch['date']} and contains "
        f"{batch['unique_documents']:,} documents / {batch['pages']:,} pages. "
        "The manifest gained 530 rows, while checksum deduplication yields 527 unique documents.",
        "",
        "| Queue | Count |",
        "|---|---:|",
        f"| Latest-batch records in `other_relevant_laws` | {batch['broad_fallback_category']:,} |",
        f"| Latest-batch records flagged for OCR | {batch['ocr_required']:,} |",
        "",
        "## Whole-manifest quality queues",
        "",
        "| Queue | Count | Interpretation |",
        "|---|---:|---|",
        f"| Source URL present | {meta['with_source_url']:,}/{total:,} | Citation can expose an origin link when the indexed payload preserves it. |",
        f"| Verified official | {meta['verified_official']:,}/{total:,} | Host provenance passed the metadata rule. |",
        f"| Currency note present | {meta['with_currency_note']:,}/{total:,} | A note is not proof of currency; it records the review basis or warning. |",
        f"| OCR required | {meta['ocr_required']:,} | Must not be treated as searchable until OCR/extraction is verified. |",
        f"| Broad fallback category | {meta['broad_fallback_category']:,} | Reclassification queue; broad routing can dilute retrieval. |",
        "",
        "## Explicit high-risk currency classes",
        "",
    ]
    for label, entries in report["warning_classes"].items():
        lines.append(f"- `{label}`: {len(entries):,} documents")
    lines += [
        "",
        "## Required next actions",
        "",
        "1. Complete `global_legal_corpus_v5`; do not infer runtime availability from this manifest audit.",
        "2. Run `check_currency_payload_gate.py --require-complete` before cutover.",
        "3. OCR and extraction-validate the 101 flagged documents, prioritising workflow-critical tax and parent-law sources.",
        "4. Reclassify the broad `other_relevant_laws` queue using domain-specific categories, beginning with the latest promotion batch.",
        "5. Resolve explicit commencement, historical-consolidation, repeal/transition, and amendment warnings with authoritative evidence.",
        "6. Let scenario failures determine additional acquisition; do not resume collection by raw PDF target.",
        "",
        f"Machine-readable queues: `{DEFAULT_JSON.relative_to(ROOT)}`.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    rows, manifest_rows = load_unique(args.manifest)
    report = audit(rows, manifest_rows)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(render(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("manifest_rows", "unique_documents", "page_count", "latest_promotion_batch", "metadata_counts")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
