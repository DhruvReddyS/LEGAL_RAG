#!/usr/bin/env python3
"""Record what this machine actually does, under a config worth quoting.

Every timing taken during the previous session is void. The machine was at
34 GB of swap with 56,369 pageouts, and a measurement taken under paging is
not merely noisy -- it is wrong in the direction that makes a real improvement
look like a regression, because the swap cost lands on whichever change
happens to run second.

So this script records the memory state *around* every measurement, not just
the timings. A run whose "before" and "after" show swap growth should be
discarded rather than reported.

Usage:
    python scripts/measure_baseline.py
    python scripts/measure_baseline.py --out docs/evidence/baseline-clean.json
    python scripts/measure_baseline.py --skip-deep      # retrieval and LLM only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# Fixed inputs. A baseline is only comparable to another baseline taken on the
# same text, so these are constants and not samples.
REFERENCE_PROMPT = (
    "Explain, in plain language and in no more than 200 words, what rights a "
    "person has when they are arrested in India, and what the police must do."
)
TTFT_TARGET_TOKENS = (2000, 6000, 13000)
DEEP_QUERIES = (
    "What is the procedure for filing an FIR?",
    "When can the police arrest someone without a warrant?",
    "What are the rights of a person who has been arrested?",
)
FILLER_SENTENCE = (
    "The officer in charge of a police station shall reduce the information to "
    "writing and read it over to the informant. "
)


def _run(command: list[str], timeout: int = 30) -> str:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return done.stdout.strip()
    except Exception as exc:  # noqa: BLE001 - a missing tool must not abort the run
        return f"<unavailable: {type(exc).__name__}: {exc}>"


def memory_state() -> dict[str, Any]:
    """Physical memory and swap, as numbers rather than a page dump."""
    page_size = 16384
    counters: dict[str, int] = {}
    for line in _run(["vm_stat"]).splitlines():
        match = re.match(r'"?([^":]+)"?:\s+(\d+)', line.strip())
        if match:
            counters[match.group(1).strip()] = int(match.group(2))

    def gigabytes(key: str) -> float:
        return round(counters.get(key, 0) * page_size / 1e9, 2)

    swap = _run(["sysctl", "-n", "vm.swapusage"])
    numbers = [float(value) for value in re.findall(r"([\d.]+)M", swap)]
    total, used, free = (numbers + [0.0, 0.0, 0.0])[:3]
    return {
        "wired_gb": gigabytes("Pages wired down"),
        "active_gb": gigabytes("Pages active"),
        "inactive_gb": gigabytes("Pages inactive"),
        "compressed_gb": gigabytes("Pages occupied by compressor"),
        "free_gb": gigabytes("Pages free"),
        "swap_total_gb": round(total / 1024, 2),
        "swap_used_gb": round(used / 1024, 2),
        "swap_free_gb": round(free / 1024, 2),
        "pageouts": counters.get("Pageouts", 0),
    }


def ollama_residency() -> dict[str, Any]:
    """What the model host is holding, and how much of it is on the GPU.

    The CPU/GPU split is the single most consequential number here. A model
    that spills to CPU decodes several times slower, and nothing in the
    application reports it.
    """
    import urllib.request

    from app.core.config import settings

    try:
        with urllib.request.urlopen(f"{settings.ollama_base_url}/api/ps", timeout=10) as response:
            payload = json.loads(response.read())
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}

    models = []
    for model in payload.get("models", []):
        total = model.get("size", 0)
        vram = model.get("size_vram", 0)
        models.append(
            {
                "name": model.get("name"),
                "resident_gb": round(total / 1e9, 2),
                "gpu_gb": round(vram / 1e9, 2),
                "gpu_percent": round(vram / total * 100, 1) if total else 0.0,
                "context_length": model.get("context_length"),
            }
        )
    return {"models": models, "raw_ps": _run(["ollama", "ps"])}


async def _generate(client, prompt: str, *, max_tokens: int) -> dict[str, Any]:
    """One generation, reported from the client's own instrumentation.

    The client already separates time to first token from queue wait. That
    distinction is not cosmetic: an earlier version of this measurement folded
    the wait into prefill and produced a prefill rate about five times too
    slow, and optimisation was aimed at that wrong number for a while.
    """
    started = time.perf_counter()
    text, metrics = await client.generate_with_metrics(prompt, num_predict=max_tokens)
    wall_ms = (time.perf_counter() - started) * 1000

    tokens = metrics.get("response_eval_count")
    eval_ms = metrics.get("ollama_eval_duration_ms")
    return {
        "ttft_ms": metrics.get("time_to_first_response_token_ms"),
        "queue_wait_ms": metrics.get("generation_queue_wait_ms"),
        "wall_ms": round(wall_ms, 1),
        "response_tokens": tokens,
        "response_characters": len(text),
        "prompt_eval_tokens": metrics.get("prompt_eval_count"),
        "prefill_ms": metrics.get("ollama_prompt_eval_duration_ms"),
        "decode_ms": eval_ms,
        "decode_tokens_per_second": metrics.get("response_tokens_per_second"),
        "prefill_tokens_per_second": (
            round(metrics["prompt_eval_count"] / (metrics["ollama_prompt_eval_duration_ms"] / 1000), 1)
            if metrics.get("prompt_eval_count") and metrics.get("ollama_prompt_eval_duration_ms")
            else None
        ),
        "done_reason": metrics.get("done_reason"),
        "load_ms": metrics.get("ollama_load_duration_ms"),
    }


async def throughput(runs: int) -> dict[str, Any]:
    """Decode rate on one fixed prompt, repeated. Three runs, all reported.

    The spread matters as much as the median: a wide spread on identical input
    means something else on the machine is competing, and the number should not
    be quoted.
    """
    from app.services.llm import OllamaClient

    client = OllamaClient()
    results = []
    try:
        for _ in range(runs):
            results.append(await _generate(client, REFERENCE_PROMPT, max_tokens=256))
    finally:
        await client.close()

    rates = [r["decode_tokens_per_second"] for r in results if r["decode_tokens_per_second"]]
    return {
        "runs": results,
        "median_tokens_per_second": round(statistics.median(rates), 2) if rates else None,
        "spread_tokens_per_second": round(max(rates) - min(rates), 2) if len(rates) > 1 else None,
    }


async def time_to_first_token() -> list[dict[str, Any]]:
    """TTFT against prompt length, which is where prefill cost shows.

    Measured from dispatch. An earlier version measured from enqueue, which
    folded queue wait into prefill and produced a prefill rate roughly five
    times too slow -- and optimisation was aimed at it for a while.
    """
    from app.services.llm import OllamaClient

    client = OllamaClient()
    measurements = []
    try:
        for target in TTFT_TARGET_TOKENS:
            # ~4 characters per token is close enough for a size sweep, and it
            # keeps the prompt reproducible without a tokeniser dependency.
            repeats = max(1, (target * 4) // len(FILLER_SENTENCE))
            prompt = FILLER_SENTENCE * repeats + "\n\nSummarise the duty above in one sentence."
            result = await _generate(client, prompt, max_tokens=16)
            measurements.append(
                {
                    "target_prompt_tokens": target,
                    "prompt_characters": len(prompt),
                    **result,
                }
            )
    finally:
        await client.close()
    return measurements


async def deep_pipeline_stages() -> list[dict[str, Any]]:
    """Per-stage timings for the Deep graph on fixed queries."""
    from app.agents.orchestrator import LegalRAGWorkflow
    from app.services.retrieval import HybridRetrievalService

    service = HybridRetrievalService()
    workflow = LegalRAGWorkflow(service)
    runs = []
    try:
        await service.warmup()
        for query in DEEP_QUERIES:
            started = time.perf_counter()
            state = await workflow.run(
                query=query, role="citizen", case_id=None, history=[]
            )
            elapsed = (time.perf_counter() - started) * 1000
            stages = {}
            for event in state.get("agent_trace", []):
                details = event.details if hasattr(event, "details") else event.get("details", {})
                node = event.node if hasattr(event, "node") else event.get("node")
                for key, value in (details or {}).items():
                    if key.endswith("_ms"):
                        stages[f"{node}.{key}"] = value
            runs.append(
                {
                    "query": query,
                    "total_ms": round(elapsed, 1),
                    "stages": stages,
                    "evidence_strength": state.get("evidence_strength"),
                    "citations": len(state.get("citations", [])),
                }
            )
    finally:
        await service.close()
    return runs


def configuration() -> dict[str, Any]:
    """Everything a number here is only meaningful alongside."""
    from app.agents.prompt_registry import prompt_versions
    from app.core.config import settings
    from app.services.health import inference_devices

    return {
        "host": {
            "model": _run(["sysctl", "-n", "hw.model"]),
            "cpu": _run(["sysctl", "-n", "machdep.cpu.brand_string"]),
            "physical_ram_gb": round(int(_run(["sysctl", "-n", "hw.memsize"]) or 0) / 1073741824, 2),
            "os": platform.platform(),
        },
        "generation_model": settings.ollama_model,
        "generation_concurrency": settings.ollama_generation_concurrency,
        "embedding_model": settings.embedding_model,
        "embedding_dimension": settings.embedding_dimension,
        "inference_devices": inference_devices(),
        "qdrant_collection": settings.qdrant_global_collection,
        # Recorded even though this script sends no prompt of its own: a Deep
        # run does, and a timing is only comparable against the same prompts.
        "prompt_versions": prompt_versions(),
        # Ollama owns sampling. Stated so a later run can confirm it matches
        # rather than assuming it did.
        "temperature": "ollama default unless overridden per request",
        "seed": "not pinned by the application",
        "note_on_sampling": (
            "Decode rate is largely insensitive to temperature, but output "
            "length is not, so max_tokens is fixed above instead."
        ),
    }


async def collect(arguments: argparse.Namespace) -> dict[str, Any]:
    before = memory_state()
    print(json.dumps({"memory_before": before}, indent=2), flush=True)
    if before["swap_used_gb"] > 2.0:
        print(
            f"\n  WARNING: {before['swap_used_gb']} GB of swap is already in use.\n"
            "  Timings taken under paging are not comparable to timings taken\n"
            "  without it. Reboot and re-run before quoting anything below.\n",
            flush=True,
        )

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": configuration(),
        "memory_before": before,
        "ollama_residency_before": ollama_residency(),
    }

    print("measuring decode throughput ...", flush=True)
    report["throughput"] = await throughput(arguments.runs)

    print("measuring time to first token ...", flush=True)
    report["time_to_first_token"] = await time_to_first_token()

    report["ollama_residency_after_llm"] = ollama_residency()

    if not arguments.skip_deep:
        print("measuring Deep pipeline stages ...", flush=True)
        report["deep_pipeline"] = await deep_pipeline_stages()

    after = memory_state()
    report["memory_after"] = after
    report["swap_grew_during_run_gb"] = round(
        after["swap_used_gb"] - before["swap_used_gb"], 2
    )
    report["pageouts_during_run"] = after["pageouts"] - before["pageouts"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--skip-deep", action="store_true")
    parser.add_argument("--out", type=Path)
    arguments = parser.parse_args()

    report = asyncio.run(collect(arguments))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = arguments.out or (ROOT / "docs/evidence" / f"baseline-{stamp}.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    throughput_result = report.get("throughput", {})
    print("\n--- summary ---")
    print(f"  decode        : {throughput_result.get('median_tokens_per_second')} tok/s "
          f"(spread {throughput_result.get('spread_tokens_per_second')})")
    for row in report.get("time_to_first_token", []):
        print(f"  ttft @{row['target_prompt_tokens']:>6} tokens : {row['ttft_ms']} ms")
    for row in report.get("deep_pipeline", []):
        print(f"  deep total    : {row['total_ms']:.0f} ms  ({row['query'][:40]}...)")
    print(f"  swap growth   : {report['swap_grew_during_run_gb']} GB "
          f"({report['pageouts_during_run']} pageouts)")
    if report["swap_grew_during_run_gb"] > 0.5:
        print("  ^ this run paged; the timings above are not a clean baseline")
    print(f"\nwrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
