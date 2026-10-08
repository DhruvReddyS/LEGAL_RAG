#!/usr/bin/env python3
"""Fail the build when the query path gets slower, or buys speed with evidence.

The correctness suite cannot see this. Nothing in 1,092 passing tests notices a
`for` loop that awaits one Qdrant call per candidate, or a second model request
added to a hot path, or an optimisation that got faster by publishing fewer
citations.

The gate is built around one measured fact: on an idle host, a Deep run is
97% language model and 0.1 seconds of everything else. Reasoning is 52.4 s of
a 65 s p50 and verification 10.1 s; retrieval is 86 ms, enrichment 16 ms,
response generation 2 ms, query understanding and role context under 1 ms.

That shape is what makes a naive end-to-end budget useless. Deep latency is
output tokens divided by the host's decode rate plus prefill, and the decode
rate is not a property of this repository: the same reasoning prompt producing
the same 597 tokens took 42.5 s on a laptop that had been hot for an hour and
26.4 s on a cool one, 14.0 against 22.6 tokens per second. A gate on Deep
end-to-end would fail on a warm afternoon and pass a genuine regression on a
cold morning.

So the gated numbers are the ones this repository actually controls:

  fast_p95_ms                     the whole Fast lane, which runs no model
  deep_non_model_overhead_p95_ms  every Deep stage that is not reasoning or
                                  verification -- the orchestration, where a
                                  serialisation or an N+1 query would show up
  deep_first_useful_output_p95_ms how long a reader waits before seeing
                                  source-backed material
  citations_per_query             so speed cannot be bought with evidence
  abstention_rate                 so speed cannot be bought by refusing more
  unsupported_claims_per_query    so speed cannot be bought by checking less

Usage:
    python scripts/check_latency_gate.py --result docs/evidence/latency/both-shipped.json
    python scripts/check_latency_gate.py --result ... --record   # set the contract
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "docs" / "evidence" / "latency" / "latency-contract.json"

SPEC = importlib.util.spec_from_file_location("latency_benchmark", ROOT / "scripts" / "latency_benchmark.py")
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)

# Stages whose cost is the model's, not this repository's.
MODEL_STAGES = frozenset({"reasoning", "verification", "query_understanding"})

# How much worse a latency number may get before the build fails. Generous on
# purpose: the point is to catch a serialisation that costs seconds, not to
# argue about twenty milliseconds of host noise.
LATENCY_TOLERANCE = 1.50

# Evidence is allowed less room than time. A 10% drop in citations across a
# query set is not noise -- the measured per-query counts are stable to the
# unit across repeats even while timings move by 40%.
QUALITY_TOLERANCE = 0.90

# Abstention and unsupported claims are failures in the upward direction.
ABSTENTION_ABSOLUTE_SLACK = 0.05
UNSUPPORTED_TOLERANCE = 1.15


def percentile(values: list[float], fraction: float) -> float | None:
    return HARNESS.percentile(values, fraction)


def _records(report: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    return [record for record in report.get("records", []) if record.get("mode") == mode]


def _series(records: list[dict[str, Any]], key: str) -> list[float]:
    return [
        float(record[key])
        for record in records
        if record.get(key) is not None and not isinstance(record.get(key), bool)
    ]


def non_model_overhead_ms(record: dict[str, Any]) -> float:
    """Every Deep stage this repository is responsible for, summed."""
    return sum(
        float(duration)
        for stage, duration in (record.get("stages_ms") or {}).items()
        if stage not in MODEL_STAGES and stage != "workflow_total"
    )


def measure(report: dict[str, Any]) -> dict[str, Any]:
    fast = _records(report, "fast")
    deep = _records(report, "deep")
    measured: dict[str, Any] = {
        "query_set_version": report.get("query_set_version"),
        "fast_runs": len(fast),
        "deep_runs": len(deep),
    }
    if fast:
        measured["fast_p95_ms"] = round(percentile(_series(fast, "wall_ms"), 0.95) or 0.0, 2)
        measured["fast_citations_per_query"] = round(
            sum(_series(fast, "citation_count")) / len(fast), 4
        )
        measured["fast_abstention_rate"] = round(
            sum(1 for record in fast if HARNESS.abstained(record)) / len(fast), 4
        )
    if deep:
        measured["deep_non_model_overhead_p95_ms"] = round(
            percentile([non_model_overhead_ms(record) for record in deep], 0.95) or 0.0, 2
        )
        first_useful = _series(deep, "time_to_first_useful_output_ms")
        if first_useful:
            measured["deep_first_useful_output_p95_ms"] = round(percentile(first_useful, 0.95) or 0.0, 2)
        measured["deep_citations_per_query"] = round(
            sum(_series(deep, "citation_count")) / len(deep), 4
        )
        measured["deep_abstention_rate"] = round(
            sum(1 for record in deep if HARNESS.abstained(record)) / len(deep), 4
        )
        measured["deep_unsupported_claims_per_query"] = round(
            sum(_series(deep, "verification_unsupported")) / len(deep), 4
        )
        # Recorded, never gated. This is the host's property, not the
        # repository's, and it is here so a reader can see whether a latency
        # move was the code or the machine.
        rate = _series(deep, "llm_decode_tokens_per_second")
        if rate:
            measured["context_deep_decode_tokens_per_second_p50"] = round(
                percentile(rate, 0.50) or 0.0, 2
            )
        measured["context_deep_end_to_end_p50_ms"] = round(
            percentile(_series(deep, "wall_ms"), 0.50) or 0.0, 2
        )
        measured["context_deep_end_to_end_p95_ms"] = round(
            percentile(_series(deep, "wall_ms"), 0.95) or 0.0, 2
        )
    return measured


LATENCY_KEYS = (
    "fast_p95_ms",
    "deep_non_model_overhead_p95_ms",
    "deep_first_useful_output_p95_ms",
)
EVIDENCE_KEYS = ("fast_citations_per_query", "deep_citations_per_query")


def check(measured: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    recorded = contract.get("measured", {})
    if contract.get("query_set_version") != measured.get("query_set_version"):
        return [
            f"query set is {measured.get('query_set_version')} but the contract was "
            f"recorded against {contract.get('query_set_version')}; these are not comparable"
        ]
    for key in LATENCY_KEYS:
        if key not in measured or key not in recorded:
            continue
        limit = float(recorded[key]) * LATENCY_TOLERANCE
        # A floor, so a contract recorded at 16 ms does not fail on 25 ms.
        limit = max(limit, float(recorded[key]) + 250.0)
        if float(measured[key]) > limit:
            failures.append(
                f"{key} is {measured[key]:,.0f} ms against a limit of {limit:,.0f} ms "
                f"(contract {float(recorded[key]):,.0f} ms)"
            )
    for key in EVIDENCE_KEYS:
        if key not in measured or key not in recorded:
            continue
        floor = float(recorded[key]) * QUALITY_TOLERANCE
        if float(measured[key]) < floor:
            failures.append(
                f"{key} fell to {measured[key]} against a floor of {floor:.3f} "
                f"(contract {recorded[key]}); speed was bought with evidence"
            )
    for key in ("fast_abstention_rate", "deep_abstention_rate"):
        if key not in measured or key not in recorded:
            continue
        ceiling = float(recorded[key]) + ABSTENTION_ABSOLUTE_SLACK
        if float(measured[key]) > ceiling:
            failures.append(
                f"{key} rose to {measured[key]} against a ceiling of {ceiling:.3f} "
                f"(contract {recorded[key]}); refusing more often is not an optimisation"
            )
    key = "deep_unsupported_claims_per_query"
    if key in measured and key in recorded:
        ceiling = max(float(recorded[key]) * UNSUPPORTED_TOLERANCE, float(recorded[key]) + 0.5)
        if float(measured[key]) > ceiling:
            failures.append(
                f"{key} rose to {measured[key]} against a ceiling of {ceiling:.3f} "
                f"(contract {recorded[key]})"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--record", action="store_true", help="Write this run as the contract")
    args = parser.parse_args()

    report = json.loads(args.result.read_text(encoding="utf-8"))
    measured = measure(report)

    warnings = report.get("environment", {}).get("validity_warnings") or []
    if warnings:
        print(f"Refusing to gate on a run with validity warnings: {warnings}", file=sys.stderr)
        return 2

    if args.record:
        args.contract.parent.mkdir(parents=True, exist_ok=True)
        args.contract.write_text(
            json.dumps(
                {
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    # Relative when it sits in the repository, absolute
                    # otherwise. A relative path passed on the command line is
                    # not under ROOT as written, and relative_to raised.
                    "source_report": str(
                        args.result.resolve().relative_to(ROOT)
                        if args.result.resolve().is_relative_to(ROOT)
                        else args.result.resolve()
                    ),
                    "label": report.get("label"),
                    "query_set_version": measured.get("query_set_version"),
                    "git_commit": report.get("environment", {}).get("git_commit"),
                    "qdrant_collection": report.get("environment", {}).get("qdrant_collection"),
                    "qdrant_points": report.get("environment", {}).get("qdrant_points"),
                    "tolerances": {
                        "latency": LATENCY_TOLERANCE,
                        "evidence": QUALITY_TOLERANCE,
                        "abstention_absolute_slack": ABSTENTION_ABSOLUTE_SLACK,
                        "unsupported_claims": UNSUPPORTED_TOLERANCE,
                    },
                    "measured": measured,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Recorded the latency contract in {args.contract}")
        print(json.dumps(measured, indent=2, sort_keys=True))
        return 0

    if not args.contract.exists():
        print(f"No contract at {args.contract}. Record one with --record.", file=sys.stderr)
        return 2
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    failures = check(measured, contract)
    print(json.dumps(measured, indent=2, sort_keys=True))
    if failures:
        print("\nLatency gate FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("\nLatency gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
