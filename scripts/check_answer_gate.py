#!/usr/bin/env python3
"""Fail the build when the answers get worse, not just the retrieval.

check_quality_gate.py defends recall and citation accuracy -- whether the
governing law comes back. This defends what happens next: whether the answer
uses it, names the grounds the statute enumerates, discloses that its
authority has been repealed, and refuses when it should.

Those are separate failures. A change can leave retrieval untouched and still
take ground coverage from 0.8 to 0.5 by shortening the reasoning window, and
the retrieval gate stays green throughout -- which is exactly what happened
in this project when a prompt change took coverage 0.67 -> 0.50.

Two kinds of check, and the difference matters:

  Metrics, gated with tolerance.  Ground coverage, currency correctness,
  abstention correctness. These vary run to run and a zero-tolerance gate on
  them fails on noise and gets switched off within a week.

  A rule, gated at zero.  Unsupported claims. The standing rule is that a
  claim whose chunk IDs are not in the retrieved set is never published.
  A rule does not get a tolerance, and it is not compared against a baseline
  -- a baseline of one violation would make the second one mergeable.

Usage:
    python scripts/check_answer_gate.py --result docs/evidence/answers-v3.json
    python scripts/check_answer_gate.py --result ... --record
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "docs" / "evidence" / "answer-quality-baseline.json"

# Higher is better for all three, so a drop past tolerance is a regression.
GATED_METRICS = ("abstention_correct", "ground_coverage", "currency_correct")

# Wider than the retrieval gate's 0.02. Generation is sampled, so the same
# question does not produce the identical answer twice, and ground coverage
# moves by one ground out of four on a single item -- 0.05 of that item.
TOLERANCE = 0.05


def _metrics(report: dict[str, Any]) -> dict[str, Any]:
    metrics = (report.get("metrics") or {}).get("overall")
    if not metrics:
        raise SystemExit("result has no metrics.overall; is this an answers-*.json?")
    return metrics


def _check_the_rule(report: dict[str, Any]) -> list[str]:
    """Unsupported claims, checked absolutely.

    Not a metric and not baselined. Publishing a claim whose evidence was
    never retrieved is the one thing the architecture exists to prevent, so
    the gate reports the offending claims rather than a number, and one is
    enough to fail.
    """
    total = _metrics(report).get("unsupported_claims_total", 0)
    if not total:
        return []
    offences = [
        f"{row['id']}: {detail}"
        for row in report.get("rows", [])
        for detail in row.get("unsupported_claim_details", [])
    ]
    return offences or [f"{total} unsupported claim(s), details not recorded"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--tolerance", type=float, default=TOLERANCE)
    parser.add_argument("--record", action="store_true")
    arguments = parser.parse_args()

    if not arguments.result.is_file():
        raise SystemExit(f"no result file at {arguments.result}")
    report = json.loads(arguments.result.read_text(encoding="utf-8"))
    metrics = _metrics(report)

    # The rule is checked before anything else and regardless of --record.
    # Recording a baseline that contains a violation would launder it into
    # the accepted state of the system.
    violations = _check_the_rule(report)
    if violations:
        print("UNSUPPORTED CLAIMS -- this is a rule, not a metric:", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        print(
            "\nA published claim cited evidence that was not retrieved. Fix the "
            "pipeline; do not record this as a baseline.",
            file=sys.stderr,
        )
        return 1

    if arguments.record or not arguments.baseline.is_file():
        payload = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "golden_set": report.get("golden_set"),
            # Without this, a later comparison is between two different
            # systems and the gate reports a regression that is a config
            # change -- the mistake that produced a false v2 regression here
            # once already, by comparing a migrated index against an
            # unmigrated one.
            "measurement_config": report.get("measurement_config"),
            "metrics": {name: metrics.get(name) for name in GATED_METRICS},
            "ground_coverage_items": metrics.get("ground_coverage_items"),
            "by_role": report.get("metrics", {}).get("by_role", {}),
        }
        arguments.baseline.parent.mkdir(parents=True, exist_ok=True)
        arguments.baseline.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"recorded {arguments.baseline}")
        for name in GATED_METRICS:
            value = metrics.get(name)
            print(f"  {name:<24} {'--' if value is None else format(value, '.3f')}")
        return 0

    baseline = json.loads(arguments.baseline.read_text(encoding="utf-8"))

    if baseline.get("golden_set") != report.get("golden_set"):
        print(
            f"  NOTE: baseline used {baseline.get('golden_set')} and this run used "
            f"{report.get('golden_set')}. Different yardsticks; re-record before "
            "trusting the comparison.",
            file=sys.stderr,
        )

    was_items = baseline.get("ground_coverage_items")
    now_items = metrics.get("ground_coverage_items")
    if was_items is not None and now_items is not None and now_items < was_items:
        # Coverage over fewer items is a smaller claim, and dropping the hard
        # ones would raise the average. That reads as an improvement and is
        # the opposite of one.
        print(
            f"  NOTE: ground coverage now averages {now_items} items, was "
            f"{was_items}. Fewer scored items makes the average easier.",
            file=sys.stderr,
        )

    failures: list[str] = []
    print(f"answer gate: against {arguments.baseline.name}")
    for name in GATED_METRICS:
        current = metrics.get(name)
        previous = (baseline.get("metrics") or {}).get(name)
        if current is None or previous is None:
            print(f"  {name:<24} {'--':>7}  not measured on both sides")
            continue
        delta = float(current) - float(previous)
        verdict = "ok"
        if delta < -arguments.tolerance:
            verdict = "REGRESSION"
            failures.append(f"{name}: {previous:.3f} -> {current:.3f} ({delta:+.3f})")
        print(
            f"  {name:<24} {float(previous):.3f} -> {float(current):.3f}  "
            f"({delta:+.3f})  {verdict}"
        )

    # Reported, not gated: an average holds while one role rots.
    for role, scores in (report.get("metrics", {}).get("by_role") or {}).items():
        was = (baseline.get("by_role") or {}).get(role, {})
        now_coverage, was_coverage = scores.get("ground_coverage"), was.get("ground_coverage")
        if now_coverage is None or was_coverage is None:
            continue
        drop = now_coverage - was_coverage
        flag = "  <-- watch" if drop < -arguments.tolerance else ""
        print(
            f"    {role:<9} coverage {was_coverage:.3f} -> {now_coverage:.3f} "
            f"({drop:+.3f}){flag}"
        )

    if failures:
        print("\nanswer gate FAILED:")
        for failure in failures:
            print(f"  {failure}")
        print(
            "\nIf this drop is intended, re-record with --record and say in the "
            "commit message why the new number is the right one."
        )
        return 1

    print("\nanswer gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
