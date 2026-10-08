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
    canonical = read_jsonl(CANONICAL)
    staged = read_jsonl(STAGED)
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    report = {
        "generated_on": date.today().isoformat(),
        "basis": "canonical manifest; physical workspaces reported separately",
        "canonical": {
            "totals": totals(canonical),
            "top_level_segments": summarize(canonical, 1),
            "categories": summarize(canonical, 99),
        },
        "staged": {"totals": totals(staged), "categories": summarize(staged, 99)},
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
    staged_total = report["staged"]["totals"]
    coverage = report["coverage"]
    lines = [
        "# Corpus segment inventory",
        "",
        f"Generated: {report['generated_on']}",
        "",
        "The canonical manifest is the production-count authority. Raw and candidate workspaces contain duplicates, rejected files, quarantined material, and review candidates, so their physical file counts are shown separately and must not be added to the canonical total.",
        "",
        "## Exact canonical total",
        "",
        "| PDFs | Pages | Bytes | GiB |",
        "|---:|---:|---:|---:|",
        f"| {canonical_total['documents']:,} | {canonical_total['pages']:,} | {canonical_total['bytes']:,} | {size_label(canonical_total['bytes'])} |",
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
        f"- Staged for promotion: {staged_total['documents']:,} PDFs, {staged_total['pages']:,} pages, {staged_total['bytes']:,} bytes ({size_label(staged_total['bytes'])}).",
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

    print(json.dumps({"canonical": canonical_total, "staged": staged_total, "coverage": coverage}, indent=2))


if __name__ == "__main__":
    main()
