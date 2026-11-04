#!/usr/bin/env python3
"""Fail the build when retrieval gets worse at finding the right law.

The correctness suite answers "does the code do what it was told". It has been
green throughout every retrieval regression this project has had, including
the one where the abstention gate silently became a no-op and four of six
known corpus gaps started being answered. Nothing in 528 passing tests
noticed, because nothing in them asks whether the right law comes back.

This is the gate that turns the verification architecture from a claim into a
defended property: a change that improves latency or tidiness, and quietly
costs recall or citation accuracy, stops being mergeable.

Two metrics are gated:

  recall_at_5            did the governing authority come back at all
  citation_accuracy_at_5 what fraction of what the reader is shown is correct

Recall alone is not enough. A change that returns five passages where three
are right scores the same recall as one returning five where all five are, and
a citizen experiences those very differently.

Usage:
    python scripts/check_quality_gate.py --result docs/evidence/eval-latest.json
    python scripts/check_quality_gate.py --result ... --record   # set baseline
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "docs" / "evidence" / "quality-baseline.json"

# The lane that actually serves users. Gating a configuration nobody runs
# would let the deployed one rot while the build stayed green.
GATED_CONFIG = "hybrid"

GATED_METRICS = ("recall_at_5", "citation_accuracy_at_5")

# Retrieval is not bit-deterministic across rebuilds of the index, so a gate
# with zero tolerance fails on noise and gets disabled within a week. This is
# wide enough to absorb that and narrow enough to catch a real loss.
TOLERANCE = 0.02

# Questions no corpus of Indian law can answer, so abstaining is a rule rather than a
# rate. Topics the corpus has since gained do not belong here: tenancy and consumer
# law are now held, and answering those can be right. An average hid this: abstention
# fell from 0.500 to 0.333 on v5 with no line in this gate's output.
MUST_ABSTAIN = ("foreign-visa",)


def _must_abstain_failures(report: dict[str, Any], config: str) -> list[str]:
    items = (report.get("configs") or {}).get(config, {}).get("items") or []
    return [
        f"{item['id']} must abstain and did not"
        for item in items
        if item.get("id") in MUST_ABSTAIN and not item.get("abstained")
    ]


def _summary(report: dict[str, Any], config: str) -> dict[str, Any]:
    configs = report.get("configs") or {}
    if config not in configs:
        raise SystemExit(
            f"result has no '{config}' configuration; found {sorted(configs)}"
        )
    return configs[config]["summary"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--config", default=GATED_CONFIG)
    parser.add_argument("--tolerance", type=float, default=TOLERANCE)
    parser.add_argument(
        "--record",
        action="store_true",
        help="write this result as the new baseline instead of checking it",
    )
    arguments = parser.parse_args()

    if not arguments.result.is_file():
        raise SystemExit(f"no result file at {arguments.result}")
    report = json.loads(arguments.result.read_text(encoding="utf-8"))
    summary = _summary(report, arguments.config)
    abstention_failures = _must_abstain_failures(report, arguments.config)
    if abstention_failures:
        print("quality gate FAILED, and this cannot be recorded into a baseline:")
        for failure in abstention_failures:
            print(f"  {failure}")
        return 1

    if not arguments.record and not arguments.baseline.is_file():
        # Recording here let a renamed file pass the gate and install a new contract.
        print(f"no baseline at {arguments.baseline}; record one deliberately with --record")
        return 2

    if arguments.record:
        payload = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "config": arguments.config,
            "collection": report.get("collection"),
            "golden_set": report.get("golden_set"),
            # Without this a later comparison is between two different systems
            # and the gate reports a regression that is really a config change.
            "measurement_config": report.get("config"),
            "metrics": {name: summary[name] for name in GATED_METRICS},
            "by_role": summary.get("by_role", {}),
        }
        arguments.baseline.parent.mkdir(parents=True, exist_ok=True)
        arguments.baseline.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"recorded {arguments.baseline}")
        for name in GATED_METRICS:
            print(f"  {name:<24} {summary[name]:.3f}")
        return 0

    baseline = json.loads(arguments.baseline.read_text(encoding="utf-8"))

    if baseline.get("golden_set") != report.get("golden_set"):
        print(
            f"  NOTE: baseline was measured against {baseline.get('golden_set')} and "
            f"this run used {report.get('golden_set')}. The comparison is between "
            "two different yardsticks; re-record before trusting it.",
            file=sys.stderr,
        )

    # The baseline sat two corpus generations behind for a month without a word.
    print(
        f"baseline: {baseline.get('collection')} recorded {baseline.get('recorded_at')}; "
        f"this run: {report.get('collection')}"
    )
    was_prompts = (baseline.get("measurement_config") or {}).get("prompt_versions") or {}
    now_prompts = (report.get("config") or {}).get("prompt_versions") or {}
    changed = sorted(name for name in was_prompts if was_prompts[name] != now_prompts.get(name))
    if changed:
        print(f"  NOTE: prompts changed since the baseline: {', '.join(changed)}")

    failures: list[str] = []
    print(f"quality gate: {arguments.config} against {arguments.baseline.name}")
    for name in GATED_METRICS:
        current = float(summary[name])
        previous = float(baseline["metrics"][name])
        delta = current - previous
        verdict = "ok"
        if delta < -arguments.tolerance:
            verdict = "REGRESSION"
            failures.append(f"{name}: {previous:.3f} -> {current:.3f} ({delta:+.3f})")
        print(f"  {name:<24} {previous:.3f} -> {current:.3f}  ({delta:+.3f})  {verdict}")

    # Reported but not gated: a role can rot while the average holds.
    for role, scores in (summary.get("by_role") or {}).items():
        was = (baseline.get("by_role") or {}).get(role, {})
        if not was:
            continue
        drop = scores["recall_at_5"] - was["recall_at_5"]
        flag = "  <-- watch" if drop < -arguments.tolerance else ""
        print(
            f"    {role:<9} R@5 {was['recall_at_5']:.3f} -> "
            f"{scores['recall_at_5']:.3f} ({drop:+.3f}){flag}"
        )

    if failures:
        print("\nquality gate FAILED:")
        for failure in failures:
            print(f"  {failure}")
        print(
            "\nIf this drop is intended, re-record the baseline with --record and "
            "say in the commit message why the new number is the right one."
        )
        return 1

    print("\nquality gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
