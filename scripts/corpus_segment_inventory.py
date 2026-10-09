#!/usr/bin/env python3
"""Generate exact PDF counts and sizes for canonical corpus segments.

The canonical manifest is the authority for production counts. Physical files
outside that manifest are reported separately because candidate, duplicate,
quarantine, and historical files must not be mistaken for runtime coverage.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data/legal_kb/metadata/canonical_documents.jsonl"
STAGED = ROOT / "data/legal_kb/metadata/canonical_documents.staged.jsonl"
AUDIT = ROOT / "docs/evidence/corpus/coverage-audit.json"
OUT_JSON = ROOT / "docs/evidence/corpus/corpus-segment-inventory.json"
OUT_MD = ROOT / "docs/evidence/corpus/CORPUS_SEGMENT_INVENTORY.md"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def unique_canonical(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirror ingestion: index one physical source per canonical content hash."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        canonical_id = str(row.get("canonical_document_id") or "")
        if canonical_id in seen:
            continue
        seen.add(canonical_id)
        unique.append(row)
    return unique


def summarize(rows: list[dict[str, Any]], depth: int) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"documents": 0, "pages": 0, "bytes": 0})
    for row in rows:
        category = str(row.get("category") or "unclassified")
        parts = category.split("/")
        key = "/".join(parts[:depth]) if len(parts) >= depth else category
        bucket = buckets[key]
        bucket["documents"] += 1
        bucket["pages"] += int(row.get("page_count") or 0)
        bucket["bytes"] += int(row.get("file_size") or 0)
    return [{"segment": key, **value} for key, value in sorted(buckets.items())]


def totals(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "documents": len(rows),
        "pages": sum(int(row.get("page_count") or 0) for row in rows),
        "bytes": sum(int(row.get("file_size") or 0) for row in rows),
    }


def physical_pdf_stats(path: Path) -> dict[str, int]:
    files = [item for item in path.rglob("*") if item.is_file() and item.suffix.lower() == ".pdf"]
    return {"files": len(files), "bytes": sum(item.stat().st_size for item in files)}


def size_label(value: int) -> str:
    return f"{value / (1024 ** 3):.3f} GiB"


def main() -> None:
    canonical_manifest = read_jsonl(CANONICAL)
    canonical = unique_canonical(canonical_manifest)
    staged = read_jsonl(STAGED)
    canonical_document_ids = {
        str(row.get("document_id") or "") for row in canonical_manifest
    }
    promoted_staged = sum(
        str(row.get("document_id") or "") in canonical_document_ids for row in staged
    )
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    report = {
        "generated_on": date.today().isoformat(),
        "basis": "canonical manifest; physical workspaces reported separately",
        "canonical": {
            "totals": totals(canonical),
            "manifest_file_records": len(canonical_manifest),
            "duplicate_file_records": len(canonical_manifest) - len(canonical),
            "top_level_segments": summarize(canonical, 1),
            "categories": summarize(canonical, 99),
        },
        "promotion_batch": {
            "totals": totals(staged),
            "now_canonical": promoted_staged,
            "awaiting_promotion": len(staged) - promoted_staged,
            "categories": summarize(staged, 99),
        },
        "physical_workspaces": {
            "data/legal_kb/raw": physical_pdf_stats(ROOT / "data/legal_kb/raw"),
            "data/source_materials/candidate_imports": physical_pdf_stats(
                ROOT / "data/source_materials/candidate_imports"
            ),
        },
        "coverage": audit["summary"],
    }
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    canonical_total = report["canonical"]["totals"]
    promotion_total = report["promotion_batch"]["totals"]
    coverage = report["coverage"]
    lines = [
        "# Corpus segment inventory",
        "",
        f"Generated: {report['generated_on']}",
        "",
        "The canonical manifest is the production-count authority. Runtime ingestion indexes one file per canonical content hash, so the segment tables are deduplicated exactly as the ingestion pipeline is. Raw and candidate workspaces contain duplicates, rejected files, quarantined material, and review candidates; their physical counts must not be added to the runtime total.",
        "",
        "## Exact canonical total",
        "",
        "| PDFs | Pages | Bytes | GiB |",
        "|---:|---:|---:|---:|",
        f"| {canonical_total['documents']:,} | {canonical_total['pages']:,} | {canonical_total['bytes']:,} | {size_label(canonical_total['bytes'])} |",
        "",
        f"The manifest contains {report['canonical']['manifest_file_records']:,} physical file records. "
        f"{report['canonical']['duplicate_file_records']:,} are byte-identical alternate copies, leaving "
        f"{canonical_total['documents']:,} unique PDFs for indexing.",
        "",
        "## Canonical PDFs by top-level segment",
        "",
        "| Segment | PDFs | Pages | Bytes | GiB |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in report["canonical"]["top_level_segments"]:
        lines.append(
            f"| `{row['segment']}` | {row['documents']:,} | {row['pages']:,} | "
            f"{row['bytes']:,} | {size_label(row['bytes'])} |"
        )
    lines += [
        "",
        "## Canonical PDFs by category",
        "",
        "| Category | PDFs | Pages | Bytes | GiB |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in report["canonical"]["categories"]:
        lines.append(
            f"| `{row['segment']}` | {row['documents']:,} | {row['pages']:,} | "
            f"{row['bytes']:,} | {size_label(row['bytes'])} |"
        )
    lines += [
        "",
        "## Review and collection state",
        "",
        f"- Last promotion batch: {promotion_total['documents']:,} PDFs, {promotion_total['pages']:,} pages, {promotion_total['bytes']:,} bytes ({size_label(promotion_total['bytes'])}); {report['promotion_batch']['now_canonical']:,} are now canonical and {report['promotion_batch']['awaiting_promotion']:,} await promotion.",
        f"- Workflow coverage: {coverage['workflows']} defined workflows; {coverage['by_status'].get('canonical_complete', coverage['by_status'].get('ready_runtime', 0))} canonical-complete and {coverage['by_status'].get('awaiting_promotion', 0)} awaiting promotion. Runtime readiness still requires index and quality gates.",
        "- Remaining metadata-level source gaps: 0. Further collection is driven by failed evaluations or unresolved currency/commencement evidence, not a target PDF count.",
        "- Two review blockers remain explicit: the CMVR base PDF is an old consolidation requiring amendment reconciliation; the AP tenancy Act requires authoritative commencement/rules evidence.",
        "",
        "## Physical workspaces (not additive)",
        "",
        "| Workspace | PDF files | Bytes | GiB |",
        "|---|---:|---:|---:|",
    ]
    for workspace, values in report["physical_workspaces"].items():
        lines.append(
            f"| `{workspace}` | {values['files']:,} | {values['bytes']:,} | {size_label(values['bytes'])} |"
        )
    lines += [
        "",
        "The raw workspace count is larger than the canonical manifest because it also preserves non-canonical files. The candidate workspace is a review backlog, not production data.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "canonical": canonical_total,
                "manifest_file_records": report["canonical"]["manifest_file_records"],
                "promotion_batch": report["promotion_batch"],
                "coverage": coverage,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
