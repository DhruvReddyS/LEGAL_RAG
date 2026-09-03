#!/usr/bin/env python3
"""Run five sequential Deep reproductions and persist timing/size evidence.

The report contains timings, counts, model metadata and machine observations.
The built-in synthetic query is retained for reproducibility; custom query text
is omitted unless explicitly requested. It never contains credentials,
generated answers or evidence text. Runs are allowed to finish so completed
downstream-node timings are not lost; the historical 180-second timeout
threshold is recorded as an observed breach.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents import reasoning_agent  # noqa: E402
from app.agents.orchestrator import LegalRAGWorkflow  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services.llm import OllamaClient  # noqa: E402
from app.services.pipeline_telemetry import capture_stage_metrics  # noqa: E402
from app.services.retrieval import HybridRetrievalService  # noqa: E402


DEFAULT_QUERY = (
    "Compare the legal duty to register information about a cognizable offence "
    "under section 154 of the Code of Criminal Procedure, 1973 and section 173 "
    "of the Bharatiya Nagarik Suraksha Sanhita, 2023. Explain commencement, "
    "transition, material procedural differences, lawful escalation after a "
    "refusal to record the information, and clearly identify any point the "
    "retrieved corpus cannot establish as current law. Use only retrieved sources."
)


def command_observation(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "error": type(exc).__name__}
    return {
        "available": True,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip()[:4000],
        "stderr": completed.stderr.strip()[:1000],
    }


def machine_observation() -> dict[str, Any]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        "process_max_rss_raw": usage.ru_maxrss,
        "ollama_ps": command_observation(["ollama", "ps"]),
    }


def llm_call_summary(stage_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [call for stage in stage_metrics for call in stage.get("llm_calls", [])]
    actual_prompt_tokens = [
        int(call["prompt_eval_count"])
        for call in calls
        if isinstance(call.get("prompt_eval_count"), (int, float))
    ]
    return {
        "call_count": len(calls),
        "actual_prompt_token_total": sum(actual_prompt_tokens),
        "actual_prompt_token_observations": len(actual_prompt_tokens),
        "max_prompt_tokens": max(actual_prompt_tokens) if actual_prompt_tokens else None,
        "max_context_window": max(
            (
                int(call["context_window"])
                for call in calls
                if isinstance(call.get("context_window"), (int, float))
            ),
            default=None,
        ),
    }


def query_observation(args: argparse.Namespace) -> dict[str, Any]:
    encoded = args.query.encode("utf-8")
    observation: dict[str, Any] = {
        "query_sha256": hashlib.sha256(encoded).hexdigest(),
        "query_characters": len(args.query),
        "query_utf8_bytes": len(encoded),
        "query_source": "built_in_synthetic" if args.query == DEFAULT_QUERY else "custom",
    }
    if args.query == DEFAULT_QUERY or args.include_query_text:
        observation["query"] = args.query
    return observation


async def execute(args: argparse.Namespace) -> dict[str, Any]:
    if args.reasoning_num_predict is not None:
        reasoning_agent.REASONING_NUM_PREDICT = args.reasoning_num_predict
    retrieval = HybridRetrievalService()
    workflow = LegalRAGWorkflow(retrieval, OllamaClient())
    records: list[dict[str, Any]] = []
    try:
        for index in range(1, args.runs + 1):
            captured: list[dict[str, Any]] = []
            before = machine_observation()
            started_ns = perf_counter_ns()
            error: dict[str, str] | None = None
            result: dict[str, Any] | None = None
            try:
                with capture_stage_metrics(captured.append):
                    result = await workflow.run(
                        query=args.query,
                        role=args.role,
                        case_id=None,
                        history=[],
                    )
            except Exception as exc:  # evidence harness must preserve failures
                error = {"type": type(exc).__name__}
            wall_ms = (perf_counter_ns() - started_ns) / 1_000_000
            final_metrics = result.get("stage_metrics", captured) if result else captured
            records.append(
                {
                    "run_number": index,
                    "run_id": result.get("run_id") if result else (
                        captured[0].get("run_id") if captured else None
                    ),
                    "started_at": captured[0].get("run_started_at") if captured else None,
                    "wall_ms": wall_ms,
                    "historical_timeout_threshold_ms": args.threshold_seconds * 1000,
                    "exceeded_historical_timeout_threshold": (
                        wall_ms > args.threshold_seconds * 1000
                    ),
                    "completed": result is not None,
                    "error": error,
                    "retry_count": int(result.get("retry_count", 0)) if result else None,
                    "citation_count": len(result.get("citations", [])) if result else None,
                    "evidence_strength": result.get("evidence_strength") if result else None,
                    "stage_metrics": final_metrics,
                    "llm_summary": llm_call_summary(final_metrics),
                    "machine_before": before,
                    "machine_after": machine_observation(),
                }
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        **query_observation(args),
                        "role": args.role,
                        "model": settings.ollama_model,
                        "reasoning_num_predict_requested": (
                            reasoning_agent.REASONING_NUM_PREDICT
                        ),
                        "runs_requested": args.runs,
                        "runs_recorded": len(records),
                        "records": records,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "run": index,
                        "completed": result is not None,
                        "wall_ms": wall_ms,
                        "threshold_exceeded": wall_ms > args.threshold_seconds * 1000,
                        "stages": len(final_metrics),
                        "output": str(args.output),
                    }
                ),
                flush=True,
            )
    finally:
        await retrieval.close()

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **query_observation(args),
        "role": args.role,
        "model": settings.ollama_model,
        "reasoning_num_predict_requested": reasoning_agent.REASONING_NUM_PREDICT,
        "runs_requested": args.runs,
        "runs_recorded": len(records),
        "records": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect five real per-node Deep timing and input-size reproductions."
    )
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--threshold-seconds", type=float, default=180.0)
    parser.add_argument(
        "--reasoning-num-predict",
        type=int,
        default=None,
        help="Benchmark-only override for the Deep reasoning output-token ceiling.",
    )
    parser.add_argument("--role", choices=("citizen", "police", "advocate", "admin"), default="citizen")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument(
        "--include-query-text",
        action="store_true",
        help="Persist custom query text; do not use this for confidential case material.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "docs" / "evidence" / "deep-triage-raw.json",
    )
    args = parser.parse_args()
    if (
        args.runs < 1
        or args.threshold_seconds <= 0
        or (args.reasoning_num_predict is not None and args.reasoning_num_predict < 1)
    ):
        parser.error("runs, threshold-seconds and reasoning-num-predict must be positive")
    return args


if __name__ == "__main__":
    arguments = parse_args()
    final_report = asyncio.run(execute(arguments))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(final_report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
