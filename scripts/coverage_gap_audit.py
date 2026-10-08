#!/usr/bin/env python3
"""Audit legal workflow coverage instead of chasing a document-count target.

The audit is deliberately metadata-only. It does not load embeddings, query
Qdrant, run Ollama, mutate the corpus, or decide that a candidate is safe to
publish. It answers one narrower question: for each supported workflow, are
the minimum authoritative instruments already canonical, waiting in staging,
downloaded for review, merely listed in a manifest, or still missing?

Usage:
    python scripts/coverage_gap_audit.py
    python scripts/coverage_gap_audit.py --requirements path/to/file.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS = ROOT / "data/source_materials/coverage_requirements_v1.json"
DEFAULT_JSON = ROOT / "docs/evidence/corpus/coverage-audit.json"
DEFAULT_MARKDOWN = ROOT / "docs/evidence/corpus/COVERAGE_AUDIT.md"


@dataclass(frozen=True)
class Record:
    title: str
    state: str
    source: str
    filename: str | None = None


STATE_RANK = {
    "canonical": 4,
    "staged": 3,
    "candidate_downloaded": 2,
    "manifest_only": 1,
}


def read_jsonl(path: Path, state: str) -> list[Record]:
    rows: list[Record] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        title = str(item.get("title") or item.get("act_name") or "").strip()
        if title:
            rows.append(Record(title=title, state=state, source=str(path.relative_to(ROOT))))
    return rows


def iter_manifest_items(path: Path) -> Iterable[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ()
    if isinstance(payload, list):
        return (item for item in payload if isinstance(item, dict))
    if isinstance(payload, dict):
        for key in ("documents", "sources", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return (item for item in value if isinstance(item, dict))
    return ()


def load_inventory() -> list[Record]:
    records = [
        *read_jsonl(
            ROOT / "data/legal_kb/metadata/canonical_documents.jsonl", "canonical"
        ),
        *read_jsonl(
            ROOT / "data/legal_kb/metadata/canonical_documents.staged.jsonl", "staged"
        ),
    ]
    candidate_dir = ROOT / "data/source_materials/candidate_imports"
    for path in sorted((ROOT / "data/source_materials").glob("*.json")):
        for item in iter_manifest_items(path):
            title = str(item.get("title") or item.get("act_name") or "").strip()
            filename = str(item.get("filename") or "").strip() or None
            if not title:
                continue
            state = (
                "candidate_downloaded"
                if filename and (candidate_dir / filename).is_file()
                else "manifest_only"
            )
            records.append(
                Record(
                    title=title,
                    state=state,
                    source=str(path.relative_to(ROOT)),
                    filename=filename,
                )
            )
    return records


def best_match(patterns: list[str], records: list[Record]) -> Record | None:
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    matches = [
        record
        for record in records
        if any(pattern.search(record.title) for pattern in compiled)
    ]
    if not matches:
        return None
    return max(matches, key=lambda record: (STATE_RANK[record.state], -len(record.title)))


def audit(requirements: dict[str, Any], records: list[Record]) -> dict[str, Any]:
    workflows: list[dict[str, Any]] = []
    for workflow in requirements["workflows"]:
        sources: list[dict[str, Any]] = []
        for source in workflow["minimum_sources"]:
            match = best_match(source["match_any"], records)
            sources.append(
                {
                    "id": source["id"],
                    "label": source["label"],
                    "required": source.get("required", True),
                    "state": match.state if match else "missing",
                    "matched_title": match.title if match else None,
                    "inventory_source": match.source if match else None,
                    "filename": match.filename if match else None,
                }
            )

        core = [source for source in sources if source["required"]]
        canonical = sum(source["state"] == "canonical" for source in core)
        available = sum(source["state"] != "missing" for source in core)
        if core and canonical == len(core):
            status = "ready_runtime"
        elif core and available == len(core):
            if any(source["state"] == "manifest_only" for source in core):
                status = "acquisition_planned"
            else:
                status = "awaiting_promotion"
        elif available:
            status = "partial"
        else:
            status = "gap"

        workflows.append(
            {
                **{key: value for key, value in workflow.items() if key != "minimum_sources"},
                "status": status,
                "core_required": len(core),
                "core_canonical": canonical,
                "core_available_any_state": available,
                "missing_core": [source["label"] for source in core if source["state"] == "missing"],
                "sources": sources,
            }
        )

    statuses = sorted({workflow["status"] for workflow in workflows})
    priorities = sorted({workflow["priority"] for workflow in workflows})
    return {
        "generated_on": date.today().isoformat(),
        "requirements_version": requirements["version"],
        "inventory_records_scanned": len(records),
        "summary": {
            "workflows": len(workflows),
            "by_status": {
                status: sum(workflow["status"] == status for workflow in workflows)
                for status in statuses
            },
            "by_priority": {
                priority: {
                    "total": sum(workflow["priority"] == priority for workflow in workflows),
                    "ready_runtime": sum(
                        workflow["priority"] == priority
                        and workflow["status"] == "ready_runtime"
                        for workflow in workflows
                    ),
                }
                for priority in priorities
            },
        },
        "workflows": workflows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Workflow coverage audit",
        "",
        f"Generated: {report['generated_on']}  ",
        f"Requirements: `{report['requirements_version']}`  ",
        f"Metadata records scanned: {report['inventory_records_scanned']:,}",
        "",
        "This report measures whether minimum authoritative sources for a legal workflow are usable in the runtime corpus. It does **not** treat document volume as quality and it does not promote candidates.",
        "",
        "## Summary",
        "",
        "| Status | Workflows | Meaning |",
        "|---|---:|---|",
    ]
    meanings = {
        "ready_runtime": "Every required source is canonical.",
        "awaiting_promotion": "All required sources exist, but at least one is staged or downloaded for review.",
        "acquisition_planned": "All required sources are identified, but at least one is not downloaded.",
        "partial": "Some required sources exist and at least one is missing.",
        "gap": "No required source was matched.",
    }
    for status in ("ready_runtime", "awaiting_promotion", "acquisition_planned", "partial", "gap"):
        lines.append(f"| `{status}` | {summary['by_status'].get(status, 0)} | {meanings[status]} |")

    lines += [
        "",
        "## Workflow matrix",
        "",
        "| Priority | Workflow | Personas | Runtime sources | Status | Missing minimum sources |",
        "|---|---|---|---:|---|---|",
    ]
    for workflow in sorted(report["workflows"], key=lambda row: (row["priority"], row["id"])):
        missing = "; ".join(workflow["missing_core"]) or "—"
        personas = ", ".join(workflow["personas"])
        lines.append(
            f"| {workflow['priority']} | {workflow['workflow']} | {personas} | "
            f"{workflow['core_canonical']}/{workflow['core_required']} | "
            f"`{workflow['status']}` | {missing} |"
        )

    lines += ["", "## Evidence by workflow", ""]
    for workflow in sorted(report["workflows"], key=lambda row: (row["priority"], row["id"])):
        lines += [
            f"### {workflow['priority']} — {workflow['workflow']}",
            "",
            f"Status: `{workflow['status']}`. Jurisdiction: {workflow['jurisdiction']}.",
            "",
            "| Minimum source | Required | State | Matched title |",
            "|---|---|---|---|",
        ]
        for source in workflow["sources"]:
            title = source["matched_title"] or "—"
            lines.append(
                f"| {source['label']} | {'yes' if source['required'] else 'supporting'} | "
                f"`{source['state']}` | {title} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    requirements = json.loads(args.requirements.read_text(encoding="utf-8"))
    report = audit(requirements, load_inventory())
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
