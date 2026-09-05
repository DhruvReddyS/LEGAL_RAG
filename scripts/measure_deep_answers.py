#!/usr/bin/env python3
"""Deep answers and what they cost, on fixed questions.

Latency work on this pipeline is only meaningful next to the answer it
produced. Reasoning spends most of the run decoding claims, so anything that
makes it faster makes the answer shorter -- and this records both, so a change
that bought speed by dropping substance is visible rather than inferred.

Usage:
    python scripts/measure_deep_answers.py --label before
    python scripts/measure_deep_answers.py --label after
    python scripts/measure_deep_answers.py --compare before after
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
OUT = ROOT / "docs" / "evidence"

QUESTIONS = [
    ("citizen", "When can the police arrest someone without a warrant?"),
    ("citizen", "What are the rights of a person who has been arrested?"),
    ("citizen", "Is a statement made by a dying person accepted as evidence?"),
    ("police", "How must chain of custody be maintained for seized material?"),
]


async def run_all() -> dict:
    from app.agents.orchestrator import LegalRAGWorkflow
    from app.agents.prompt_registry import prompt_versions
    from app.core.config import settings
    from app.services.retrieval import HybridRetrievalService

    service = HybridRetrievalService()
    workflow = LegalRAGWorkflow(service)
    rows = []
    try:
        await service.warmup()
        for role, question in QUESTIONS:
            started = time.perf_counter()
            state = await workflow.run(
                query=question, role=role, case_id=None, history=[]
            )
            elapsed = (time.perf_counter() - started) * 1000

            stages = {}
            output_tokens = 0
            llm_calls = 0
            for metric in state.get("stage_metrics", []):
                name = metric.get("stage")
                if name in {"workflow_total"}:
                    continue
                stages[name] = round(metric.get("duration_ms", 0), 0)
                for call in metric.get("llm_calls") or []:
                    llm_calls += 1
                    output_tokens += call.get("response_eval_count") or 0

            answer = state.get("final_answer") or state.get("answer") or ""
            citations = state.get("citations", [])
            claims = state.get("claims", []) or state.get("verified_claims", [])
            rows.append(
                {
                    "role": role,
                    "question": question,
                    "total_ms": round(elapsed, 0),
                    "stages_ms": stages,
                    "llm_calls": llm_calls,
                    "output_tokens": output_tokens,
                    "answer_words": len(str(answer).split()),
                    "answer": str(answer),
                    "citations": len(citations),
                    "claims": len(claims),
                    "evidence_strength": state.get("evidence_strength"),
                }
            )
            print(
                f"  {elapsed/1000:6.1f} s  {output_tokens:>5} out tok  "
                f"{len(str(answer).split()):>4} words  {len(citations)} cites  {question[:44]}",
                flush=True,
            )
    finally:
        await service.close()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection": settings.qdrant_global_collection,
        "generation_model": settings.ollama_model,
        "prompt_versions": prompt_versions(),
        "max_claims": __import__("app.agents.reasoning_agent", fromlist=["MAX_CLAIMS"]).MAX_CLAIMS,
        "max_claim_characters": __import__(
            "app.agents.reasoning_agent", fromlist=["MAX_CLAIM_CHARACTERS"]
        ).MAX_CLAIM_CHARACTERS,
        "runs": rows,
    }


def compare(before: Path, after: Path) -> None:
    a = json.loads(before.read_text(encoding="utf-8"))
    b = json.loads(after.read_text(encoding="utf-8"))
    print(f"\n{'question':<46}{'before':>18}{'after':>18}")
    for x, y in zip(a["runs"], b["runs"], strict=False):
        print(f"\n  {x['question'][:44]}")
        for key, unit in (
            ("total_ms", "s"),
            ("output_tokens", "tok"),
            ("answer_words", "words"),
            ("citations", "cites"),
            ("llm_calls", "calls"),
        ):
            va, vb = x.get(key, 0), y.get(key, 0)
            if unit == "s":
                va, vb = va / 1000, vb / 1000
                print(f"    {key:<18}{va:>10.1f}{unit:<4}{vb:>13.1f}{unit}   {vb-va:+.1f}")
            else:
                print(f"    {key:<18}{va:>10}{unit:<6}{vb:>11}{unit}   {vb-va:+d}")
    ta = sum(r["total_ms"] for r in a["runs"]) / len(a["runs"]) / 1000
    tb = sum(r["total_ms"] for r in b["runs"]) / len(b["runs"]) / 1000
    print(f"\n  mean total: {ta:.1f} s -> {tb:.1f} s  ({(tb-ta)/ta*100:+.0f}%)")
    print(f"  claims cap: {a['max_claims']} -> {b['max_claims']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    arguments = parser.parse_args()

    if arguments.compare:
        compare(*(OUT / f"deep-answers-{name}.json" for name in arguments.compare))
        return 0

    label = arguments.label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = asyncio.run(run_all())
    OUT.mkdir(parents=True, exist_ok=True)
    destination = OUT / f"deep-answers-{label}.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    mean = sum(r["total_ms"] for r in report["runs"]) / len(report["runs"]) / 1000
    print(f"\n  mean {mean:.1f} s over {len(report['runs'])} questions")
    print(f"  wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
