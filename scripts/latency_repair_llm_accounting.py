#!/usr/bin/env python3
"""Re-derive a latency report's LLM accounting from the persisted job results.

The first baseline's `stage_breakdown` read `response_prompt_eval_count` and
`duration_ms`, neither of which the pipeline writes, so every prompt-token and
LLM-duration figure came back as zero. A zero there reads as "no cost" rather
than "not measured", which is the more dangerous of the two mistakes.

The measurement itself is not lost: a Deep job stores its complete
`pipeline_metrics` in `jobs.result`, so the prefill/decode split can be
recovered without spending another forty minutes on the machine. This repairs
the report in place from the database, by matching the benchmark cohort's
successful Deep jobs in creation order against the report's records in the
order the harness ran them.

The match is positional because the first harness did not record a job id. It
is checked rather than assumed: the stored answer must match the record's
answer, and the run is rejected if any pair disagrees.

Usage:
    python scripts/latency_repair_llm_accounting.py \
        --report docs/evidence/latency/both-baseline.json --cohort 1ba954c0c09a
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

SPEC = importlib.util.spec_from_file_location("latency_benchmark", ROOT / "scripts" / "latency_benchmark.py")
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


async def stored_deep_runs(cohort: str) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models import Job, User
    from app.models.enums import JobStatus, JobType

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Job.id, Job.result, Job.created_at)
                .join(User, User.id == Job.user_id)
                .where(
                    User.email.like(f"latency-bench-{cohort}-%"),
                    Job.type == JobType.DEEP_REVIEW,
                    Job.status == JobStatus.SUCCEEDED,
                )
                .order_by(Job.created_at)
            )
        ).all()
    return [
        {"job_id": str(job_id), "result": result or {}, "created_at": created_at.isoformat()}
        for job_id, result, created_at in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cohort", required=True, help="The cohort hex in the benchmark account emails")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    records = [record for record in report["records"] if record["mode"] == "deep"]
    stored = asyncio.run(stored_deep_runs(args.cohort))

    # The harness discards one warm-up per mode. It is the first job the
    # cohort ran, so the stored list is one longer than the record list.
    if len(stored) == len(records) + 1:
        stored = stored[1:]
    if len(stored) != len(records):
        raise SystemExit(
            f"Refusing to repair: {len(stored)} stored Deep jobs for cohort "
            f"{args.cohort} against {len(records)} records in the report. "
            "A positional match needs these to correspond exactly."
        )

    mismatches: list[str] = []
    for index, (record, row) in enumerate(zip(records, stored, strict=True)):
        stored_answer = str((row["result"] or {}).get("answer") or "")
        if stored_answer.strip() != str(record.get("answer") or "").strip():
            mismatches.append(f"record {index} ({record['query_id']})")
    if mismatches:
        raise SystemExit(
            "Refusing to repair: the stored answer differs from the recorded "
            f"answer for {len(mismatches)} run(s): {', '.join(mismatches[:5])}. "
            "The positional match is wrong, so the cohort or the report is not "
            "the one this run produced."
        )

    repaired = 0
    for record, row in zip(records, stored, strict=True):
        metrics = (row["result"] or {}).get("pipeline_metrics") or []
        breakdown = HARNESS.stage_breakdown(metrics)
        record.update(breakdown)
        record["job_id"] = row["job_id"]
        record["pipeline_metrics"] = metrics
        repaired += 1

    report.setdefault("repairs", []).append(
        {
            "what": "LLM accounting re-derived from jobs.result",
            "why": (
                "stage_breakdown read key names the pipeline does not write, so "
                "prompt tokens, prefill, decode and LLM duration were recorded as zero"
            ),
            "cohort": args.cohort,
            "records_repaired": repaired,
            "matched_on": "successful Deep jobs in creation order, verified against the stored answer text",
        }
    )
    if args.dry_run:
        print(json.dumps(HARNESS.stage_breakdown((stored[0]["result"] or {}).get("pipeline_metrics") or []), indent=2))
        print(f"\nWould repair {repaired} records in {args.report}")
        return
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Repaired {repaired} Deep records in {args.report}")


if __name__ == "__main__":
    main()
