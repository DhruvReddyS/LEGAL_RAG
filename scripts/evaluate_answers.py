#!/usr/bin/env python3
"""Answer quality on the golden set, measured rather than read.

This drives the real workflow -- the same object the API routes call -- and
scores what comes back. It deliberately reimplements nothing: an earlier
harness in this project scored a list retrieval never published and reported
numbers the product could not reproduce, four separate times. Anything the
lane decides, the lane decides here too.

Usage:
    python scripts/evaluate_answers.py --label v3
    python scripts/evaluate_answers.py --label v3 --only citizen
    python scripts/evaluate_answers.py --compare v2 v3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / "docs" / "evidence"
GOLDEN = ROOT / "data/legal_kb/evaluation/golden_set_v3.json"


def _run(command: list[str]) -> str:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=30)
        return done.stdout.strip()
    except Exception as exc:  # noqa: BLE001 - a missing tool must not abort a run
        return f"<unavailable: {type(exc).__name__}: {exc}>"


def memory_state() -> dict[str, Any]:
    """Whether the machine was paging, recorded with the numbers it produced.

    Required by the measurement rules for a reason: on this machine the
    models alone are 13.93 GB of a 24 GB ceiling, and a run taken under
    paging attributes the paging cost to whatever change is being tested.
    """
    swap = _run(["sysctl", "-n", "vm.swapusage"])
    numbers = [float(v) for v in re.findall(r"([\d.]+)M", swap)]
    total, used, free = (numbers + [0.0, 0.0, 0.0])[:3]
    pageouts = 0
    for line in _run(["vm_stat"]).splitlines():
        match = re.match(r'"?([^":]+)"?:\s+(\d+)', line.strip())
        if match and match.group(1).strip() == "Pageouts":
            pageouts = int(match.group(2))
    return {
        "swap_used_gb": round(used / 1024, 2),
        "swap_total_gb": round(total / 1024, 2),
        "pageouts": pageouts,
        "was_swapping": used > 64,
    }


async def run(only_role: str | None) -> dict[str, Any]:
    from app.agents.orchestrator import LegalRAGWorkflow
    from app.agents.prompt_registry import prompt_versions
    from app.core.config import settings
    from app.evaluation.answer_quality import assess_answer
    from app.services.retrieval import HybridRetrievalService

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    items = [i for i in golden["items"] if not only_role or i.get("role") == only_role]

    before = memory_state()
    service = HybridRetrievalService()
    workflow = LegalRAGWorkflow(service)
    rows: list[dict[str, Any]] = []
    try:
        await service.warmup()
        for index, item in enumerate(items, 1):
            started = time.perf_counter()
            state = await workflow.run(
                query=item["question"], role=item["role"], case_id=None, history=[]
            )
            elapsed_ms = (time.perf_counter() - started) * 1000

            quality = assess_answer(
                state,
                item_id=item["id"],
                role=item["role"],
                expectation=item["expectation"],
                grounds=item.get("grounds", ()),
            )
            row = quality.as_row()
            row["latency_ms"] = round(elapsed_ms)
            row["answer_words"] = len(str(state.get("final_answer") or "").split())
            row["citations"] = len(state.get("citations") or [])
            row["answer"] = str(state.get("final_answer") or "")
            rows.append(row)

            flag = " " if row["abstention_correct"] else "!"
            coverage = row["ground_coverage"]
            coverage_text = "  --  " if coverage is None else f"{coverage:5.2f} "
            print(
                f" {flag}{index:>3}/{len(items)} {item['role']:<9}{item['id']:<30}"
                f"{elapsed_ms/1000:6.1f}s  cov {coverage_text} "
                f"unsup {row['unsupported_claims']}  cur "
                f"{row['currency_satisfied']}/{row['currency_required']}",
                flush=True,
            )
    finally:
        await service.close()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_set": GOLDEN.name,
        "measurement_config": {
            "collection": settings.qdrant_global_collection,
            "generation_model": settings.ollama_model,
            "embedding_model": "BAAI/bge-m3",
            "temperature": getattr(settings, "ollama_temperature", None),
            "seed": getattr(settings, "ollama_seed", None),
            "prompt_versions": prompt_versions(),
            "memory_before": before,
            "memory_after": memory_state(),
        },
        "metrics": aggregate(rows),
        "rows": rows,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll the per-question rows up, without averaging them together.

    Each metric keeps its own denominator. Ground coverage is averaged only
    over the items that have authored grounds, because folding in the
    unauthored ones would let the number rise whenever a question was added
    without expectations -- improvement by omission.
    """

    def _by(rows_subset: list[dict[str, Any]]) -> dict[str, Any]:
        graded = [r for r in rows_subset if r["ground_coverage"] is not None]
        currency = [r for r in rows_subset if r["currency_required"]]
        readable = [r for r in rows_subset if r["reading_grade"] is not None]
        return {
            "items": len(rows_subset),
            "abstention_correct": round(
                sum(r["abstention_correct"] for r in rows_subset) / max(len(rows_subset), 1), 3
            ),
            "unsupported_claims_total": sum(r["unsupported_claims"] for r in rows_subset),
            "ground_coverage": (
                round(sum(r["ground_coverage"] for r in graded) / len(graded), 3)
                if graded else None
            ),
            "ground_coverage_items": len(graded),
            "currency_correct": (
                round(sum(r["currency_correct"] for r in currency) / len(currency), 3)
                if currency else None
            ),
            "currency_items": len(currency),
            "reading_grade_mean": (
                round(sum(r["reading_grade"] for r in readable) / len(readable), 1)
                if readable else None
            ),
            "latency_p50_s": (
                round(sorted(r["latency_ms"] for r in rows_subset)[len(rows_subset) // 2] / 1000, 1)
                if rows_subset else None
            ),
        }

    out = {"overall": _by(rows), "by_role": {}}
    for role in sorted({r["role"] for r in rows}):
        out["by_role"][role] = _by([r for r in rows if r["role"] == role])
    return out


def report(payload: dict[str, Any]) -> None:
    metrics = payload["metrics"]
    print("\n" + "=" * 78)
    header = f"{'':<12}{'items':>6}{'abstain':>9}{'unsup':>7}{'ground':>8}{'currency':>10}{'grade':>7}{'p50 s':>8}"
    print(header)
    print("-" * 78)
    for name, m in [("overall", metrics["overall"]), *sorted(metrics["by_role"].items())]:
        def fmt(value: Any, spec: str = "5.2f") -> str:
            return "   -- " if value is None else format(value, spec)
        print(
            f"{name:<12}{m['items']:>6}{fmt(m['abstention_correct']):>9}"
            f"{m['unsupported_claims_total']:>7}{fmt(m['ground_coverage']):>8}"
            f"{fmt(m['currency_correct']):>10}{fmt(m['reading_grade_mean'], '5.1f'):>7}"
            f"{fmt(m['latency_p50_s'], '6.1f'):>8}"
        )
    print("=" * 78)

    wrong = [r for r in payload["rows"] if not r["abstention_correct"]]
    if wrong:
        print(f"\nabstention wrong on {len(wrong)}:")
        for r in wrong:
            got = "abstained" if r["abstained"] else "answered"
            print(f"  {r['id']:<32} expected {r['expectation']}, {got}")

    unsup = [r for r in payload["rows"] if r["unsupported_claims"]]
    if unsup:
        print(f"\nUNSUPPORTED CLAIMS on {len(unsup)} -- this must be zero:")
        for r in unsup:
            for detail in r["unsupported_claim_details"]:
                print(f"  {r['id']:<32} {detail}")

    gaps = [r for r in payload["rows"] if r["grounds_missed"]]
    if gaps:
        print("\ngrounds missed:")
        for r in sorted(gaps, key=lambda r: r["ground_coverage"] or 0):
            print(f"  {r['id']:<32} {r['ground_coverage']:.2f}")
            for name in r["grounds_missed"]:
                print(f"      - {name}")

    cur = [r for r in payload["rows"] if not r["currency_correct"]]
    if cur:
        print("\ncurrency not disclosed:")
        for r in cur:
            for detail in r["currency_missing"]:
                print(f"  {r['id']:<32} {detail}")


def compare(before: Path, after: Path) -> None:
    a, b = (json.loads(p.read_text(encoding="utf-8")) for p in (before, after))
    print(f"\n{'metric':<26}{before.stem:>22}{after.stem:>22}")
    print("-" * 70)
    for key, spec in [
        ("abstention_correct", "5.3f"),
        ("unsupported_claims_total", "d"),
        ("ground_coverage", "5.3f"),
        ("currency_correct", "5.3f"),
        ("reading_grade_mean", "5.1f"),
        ("latency_p50_s", "6.1f"),
    ]:
        va, vb = a["metrics"]["overall"].get(key), b["metrics"]["overall"].get(key)
        fa = "   -- " if va is None else format(va, spec)
        fb = "   -- " if vb is None else format(vb, spec)
        delta = "" if va is None or vb is None else f"   {vb - va:+.3f}"
        print(f"{key:<26}{fa:>22}{fb:>22}{delta}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", help="write docs/evidence/answers-<label>.json")
    parser.add_argument("--only", help="restrict to one role")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    arguments = parser.parse_args()

    if arguments.compare:
        compare(*(OUT / f"answers-{n}.json" for n in arguments.compare))
        return 0
    if not arguments.label:
        parser.error("--label is required unless --compare is used")

    payload = asyncio.run(run(arguments.only))
    report(payload)
    destination = OUT / f"answers-{arguments.label}.json"
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {destination.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
