#!/usr/bin/env python3
"""Compare two latency reports under one set of definitions.

Written separately from the harness on purpose. A metric definition that
changes between a before run and an after run produces a difference that is
not a difference, and two definitions in this project drifted while the code
looked identical. Everything reported here is recomputed from the stored
records of both runs by the same code, so a definition corrected after the
baseline was recorded applies to the baseline too.

Usage:
    python scripts/latency_compare.py \
        --before docs/evidence/latency/both-baseline.json \
        --after  docs/evidence/latency/both-after.json \
        --output docs/evidence/latency/comparison.md
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("latency_benchmark", ROOT / "scripts" / "latency_benchmark.py")
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


def _records(report: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    return [record for record in report.get("records", []) if record.get("mode") == mode]


def _series(records: list[dict[str, Any]], key: str) -> list[float]:
    return [
        float(record[key])
        for record in records
        if record.get(key) is not None and not isinstance(record.get(key), bool)
    ]


def _stage_series(records: list[dict[str, Any]]) -> dict[str, list[float]]:
    stages: dict[str, list[float]] = {}
    for record in records:
        for stage, duration in (record.get("stages_ms") or {}).items():
            stages.setdefault(stage, []).append(float(duration))
    return stages


def _timing_series(records: list[dict[str, Any]]) -> dict[str, list[float]]:
    timings: dict[str, list[float]] = {}
    for record in records:
        for name, value in (record.get("timings_ms") or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                timings.setdefault(name, []).append(float(value))
    return timings


def _rate(records: list[dict[str, Any]], predicate) -> float | None:
    if not records:
        return None
    return round(sum(1 for record in records if predicate(record)) / len(records), 4)


def _delta(before: float | None, after: float | None) -> str:
    if before is None or after is None:
        return "—"
    if before == 0:
        return f"{after - before:+,.2f}"
    return f"{after - before:+,.2f} ({(after - before) / before * 100:+.1f}%)"


def _ms(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


def _p(values: list[float], fraction: float) -> float | None:
    return HARNESS.percentile(values, fraction)


def _quality_rows(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[tuple[str, str, str, str]]:
    """Recomputed from both runs' stored answers, never read from a summary."""
    def mean(records: list[dict[str, Any]], key: str) -> float | None:
        values = _series(records, key)
        return round(sum(values) / len(values), 3) if values else None

    rows: list[tuple[str, str, str, str]] = []
    metrics = [
        ("Citations per query (mean)", lambda rows_: mean(rows_, "citation_count")),
        ("Distinct source titles (mean)", lambda rows_: mean(rows_, "distinct_source_titles")),
        ("Distinct source types (mean)", lambda rows_: mean(rows_, "distinct_source_types")),
        ("Citations naming a section (mean)", lambda rows_: mean(rows_, "citations_with_section")),
        ("Citations with a source URL (mean)", lambda rows_: mean(rows_, "citations_with_url")),
        ("Answer words (mean)", lambda rows_: mean(rows_, "answer_words")),
        ("Verification score (mean)", lambda rows_: mean(rows_, "verification_score")),
        ("Verified claims (mean)", lambda rows_: mean(rows_, "verification_claims")),
        ("Unsupported claims per query (mean)", lambda rows_: mean(rows_, "verification_unsupported")),
        ("Unadjudicated claims per query (mean)", lambda rows_: mean(rows_, "verification_unadjudicated")),
        (
            "Abstention rate",
            lambda rows_: _rate(rows_, lambda record: HARNESS.abstained(record)),
        ),
        (
            "Published but graded insufficient",
            lambda rows_: _rate(
                rows_,
                lambda record: record.get("evidence_strength") == "insufficient"
                and not HARNESS.abstained(record),
            ),
        ),
        ("LLM calls per query (mean)", lambda rows_: mean(rows_, "llm_call_count")),
        ("LLM prompt tokens per query (mean)", lambda rows_: mean(rows_, "llm_prompt_tokens")),
        ("LLM output tokens per query (mean)", lambda rows_: mean(rows_, "llm_output_tokens")),
    ]
    for label, compute in metrics:
        first = compute(before)
        second = compute(after)
        if first is None and second is None:
            continue
        rows.append((label, "—" if first is None else f"{first}", "—" if second is None else f"{second}", _delta(first, second)))
    return rows


def render(before: dict[str, Any], after: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Fast and Deep latency: before and after")
    lines.append("")
    lines.append(
        f"Before: `{before.get('label')}` recorded {before.get('generated_at')}  \n"
        f"After: `{after.get('label')}` recorded {after.get('generated_at')}"
    )
    lines.append("")
    if before.get("query_set_version") != after.get("query_set_version"):
        lines.append(
            f"> **The query sets differ** "
            f"(`{before.get('query_set_version')}` vs `{after.get('query_set_version')}`). "
            "These numbers are not comparable."
        )
        lines.append("")
    for name, report in (("Before", before), ("After", after)):
        environment = report.get("environment", {})
        lines.append(
            f"- {name}: commit `{str(environment.get('git_commit'))[:12]}`, "
            f"collection `{environment.get('qdrant_collection')}` "
            f"({environment.get('qdrant_points')} points), "
            f"embedding on `{(environment.get('health_ready') or {}).get('inference', {}).get('embedding')}`, "
            f"load {', '.join(f'{value:.2f}' for value in (environment.get('load_average') or []))}, "
            f"swapouts/s {environment.get('swapout_pages_per_second')}, "
            f"queue depth at start {environment.get('initial_job_queue_depth')}"
        )
    lines.append("")

    for mode in ("fast", "deep"):
        rows_before = _records(before, mode)
        rows_after = _records(after, mode)
        if not rows_before and not rows_after:
            continue
        lines.append(f"## {mode.capitalize()}")
        lines.append("")
        lines.append(f"{len(rows_before)} runs before, {len(rows_after)} after.")
        lines.append("")
        lines.append("| Measure | Before (ms) | After (ms) | Delta |")
        lines.append("|---|---:|---:|---:|")
        for label, key, fraction in [
            ("End-to-end p50", "wall_ms", 0.50),
            ("End-to-end p95", "wall_ms", 0.95),
            ("End-to-end max", "wall_ms", 1.00),
            ("Time to first useful output p50", "time_to_first_useful_output_ms", 0.50),
            ("Time to first useful output p95", "time_to_first_useful_output_ms", 0.95),
            ("Time to first final output p50", "time_to_first_final_output_ms", 0.50),
            ("Time to first final output p95", "time_to_first_final_output_ms", 0.95),
            ("Time to first progress p50", "time_to_first_progress_ms", 0.50),
        ]:
            first = _p(_series(rows_before, key), fraction)
            second = _p(_series(rows_after, key), fraction)
            if first is None and second is None:
                continue
            lines.append(f"| {label} | {_ms(first)} | {_ms(second)} | {_delta(first, second)} |")
        lines.append("")

        stage_before = {**_stage_series(rows_before), **{f"timing:{k}": v for k, v in _timing_series(rows_before).items()}}
        stage_after = {**_stage_series(rows_after), **{f"timing:{k}": v for k, v in _timing_series(rows_after).items()}}
        stages = sorted(set(stage_before) | set(stage_after))
        if stages:
            lines.append("### Per stage, p50 then p95 (ms)")
            lines.append("")
            lines.append("| Stage | Before p50 | After p50 | Before p95 | After p95 | p50 delta |")
            lines.append("|---|---:|---:|---:|---:|---:|")
            for stage in stages:
                first_50 = _p(stage_before.get(stage, []), 0.50)
                second_50 = _p(stage_after.get(stage, []), 0.50)
                first_95 = _p(stage_before.get(stage, []), 0.95)
                second_95 = _p(stage_after.get(stage, []), 0.95)
                lines.append(
                    f"| {stage} | {_ms(first_50)} | {_ms(second_50)} | "
                    f"{_ms(first_95)} | {_ms(second_95)} | {_delta(first_50, second_50)} |"
                )
            lines.append("")

        lines.append("### Answer quality")
        lines.append("")
        lines.append("| Measure | Before | After | Delta |")
        lines.append("|---|---:|---:|---:|")
        for label, first, second, delta in _quality_rows(rows_before, rows_after):
            lines.append(f"| {label} | {first} | {second} | {delta} |")
        lines.append("")

        lines.append("### Per query")
        lines.append("")
        lines.append(
            "| Query | Before p50 (s) | After p50 (s) | Cites before | Cites after | "
            "Words before | Words after | Abstained before | Abstained after |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---|---|")
        query_ids = sorted({record["query_id"] for record in rows_before + rows_after})
        for query_id in query_ids:
            first_rows = [record for record in rows_before if record["query_id"] == query_id]
            second_rows = [record for record in rows_after if record["query_id"] == query_id]
            first_wall = _p(_series(first_rows, "wall_ms"), 0.5)
            second_wall = _p(_series(second_rows, "wall_ms"), 0.5)

            def one(rows_: list[dict[str, Any]], key: str) -> str:
                values = sorted({record.get(key) for record in rows_ if record.get(key) is not None})
                return "—" if not values else "/".join(str(value) for value in values)

            def refused(rows_: list[dict[str, Any]]) -> str:
                # Recomputed here too. Reading the stored `abstained` flag
                # would reintroduce the definition the aggregate above
                # deliberately recomputes.
                if not rows_:
                    return "—"
                values = sorted({HARNESS.abstained(record) for record in rows_})
                return "/".join(str(value) for value in values)

            lines.append(
                f"| {query_id} "
                f"| {'—' if first_wall is None else f'{first_wall / 1000:.2f}'} "
                f"| {'—' if second_wall is None else f'{second_wall / 1000:.2f}'} "
                f"| {one(first_rows, 'citation_count')} | {one(second_rows, 'citation_count')} "
                f"| {one(first_rows, 'answer_words')} | {one(second_rows, 'answer_words')} "
                f"| {refused(first_rows)} | {refused(second_rows)} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    rendered = render(before, after)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Wrote {args.output}")
    print(rendered)


if __name__ == "__main__":
    main()
