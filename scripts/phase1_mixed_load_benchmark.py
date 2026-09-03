#!/usr/bin/env python3
"""Run one real one-Deep/three-Fast Phase 1 load scenario.

The evidence excludes credentials and answer text. A unique four-user cohort is
created for each run so per-user admission limits and sessions are realistic.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import psutil


FAST_QUERIES = [
    "Is registration of an FIR mandatory when disclosed facts show a cognizable offence?",
    "Which verified statutory passages address equality before law under Article 14?",
    "What legal steps and complaint details are relevant when a pet dog is missing?",
]
DEEP_QUERY = (
    "A complainant reports that police declined to register information alleging a cognizable "
    "offence. Analyze the procedural options, evidentiary gaps, counterarguments, and limits of "
    "the available authorities. Cite only retrieved sources and abstain where support is absent."
)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def token_rates(value: Any) -> list[float]:
    rates: list[float] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "response_tokens_per_second" and isinstance(child, (int, float)):
                rates.append(float(child))
            else:
                rates.extend(token_rates(child))
    elif isinstance(value, list):
        for child in value:
            rates.extend(token_rates(child))
    return rates


def metric_values(value: Any, target_key: str) -> list[float]:
    values: list[float] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == target_key and isinstance(child, (int, float)):
                values.append(float(child))
            else:
                values.extend(metric_values(child, target_key))
    elif isinstance(value, list):
        for child in value:
            values.extend(metric_values(child, target_key))
    return values


async def register(client: httpx.AsyncClient, cohort: str, index: int, password: str) -> str:
    response = await client.post(
        "/auth/register",
        json={
            "name": f"Phase 1 Load User {index}",
            "email": f"phase1-load-{cohort}-{index}@example.com",
            "password": password,
            "role": "citizen",
        },
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


async def run(args: argparse.Namespace) -> dict[str, Any]:
    password = os.environ.get("LEGAL_RAG_BENCHMARK_PASSWORD")
    if not password:
        raise SystemExit("Set LEGAL_RAG_BENCHMARK_PASSWORD; it is never written to evidence.")
    cohort = uuid.uuid4().hex[:12]
    timeout = httpx.Timeout(args.timeout, connect=10)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout) as client:
        tokens = await asyncio.gather(
            *(register(client, cohort, index, password) for index in range(4))
        )
        headers = [{"Authorization": f"Bearer {token}"} for token in tokens]

        enqueue_started = time.perf_counter_ns()
        deep_response = await client.post(
            "/jobs/deep-review",
            headers={**headers[0], "Idempotency-Key": f"load-{cohort}"},
            json={"query": DEEP_QUERY},
        )
        enqueue_ms = (time.perf_counter_ns() - enqueue_started) / 1_000_000
        deep_response.raise_for_status()
        job_id = str(deep_response.json()["id"])
        scenario_started_ns = enqueue_started
        resource_samples: list[dict[str, Any]] = []
        sampling_done = asyncio.Event()

        async def sample_resources() -> None:
            while not sampling_done.is_set():
                sample: dict[str, Any] = {
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "host_cpu_percent": psutil.cpu_percent(interval=None),
                    "host_memory_used_bytes": psutil.virtual_memory().used,
                    "host_memory_percent": psutil.virtual_memory().percent,
                }
                try:
                    raw = await asyncio.to_thread(
                        subprocess.check_output,
                        [
                            "docker",
                            "stats",
                            "--no-stream",
                            "--format",
                            "{{json .}}",
                            "multi-agent-legal-rag-backend-1",
                        ],
                        text=True,
                        timeout=5,
                    )
                    sample["backend_container"] = json.loads(raw)
                except Exception as exc:
                    sample["backend_container_error"] = type(exc).__name__
                try:
                    ollama = await client.get("http://127.0.0.1:11434/api/ps")
                    ollama.raise_for_status()
                    sample["ollama_models"] = [
                        {
                            "name": model.get("name"),
                            "size": model.get("size"),
                            "size_vram": model.get("size_vram"),
                            "context_length": model.get("context_length"),
                        }
                        for model in ollama.json().get("models", [])
                    ]
                except Exception as exc:
                    sample["ollama_error"] = type(exc).__name__
                resource_samples.append(sample)
                try:
                    await asyncio.wait_for(sampling_done.wait(), timeout=5)
                except TimeoutError:
                    pass

        resource_task = asyncio.create_task(sample_resources())
        first_progress: dict[str, Any] | None = None
        progress_ready = asyncio.Event()
        events_seen: list[dict[str, Any]] = []

        async def consume_events() -> None:
            nonlocal first_progress
            async with client.stream(
                "GET", f"/jobs/{job_id}/events", headers=headers[0]
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    events_seen.append(
                        {
                            "id": event["id"],
                            "event_type": event["event_type"],
                            "stage": event["stage"],
                            "progress": event["progress"],
                            "created_at": event["created_at"],
                        }
                    )
                    if first_progress is None and event["stage"] not in {"queued", None}:
                        first_progress = {
                            **events_seen[-1],
                            "wall_ms_after_enqueue_start": (
                                time.perf_counter_ns() - enqueue_started
                            )
                            / 1_000_000,
                        }
                        progress_ready.set()

        event_task = asyncio.create_task(consume_events())
        await asyncio.wait_for(progress_ready.wait(), timeout=10)

        async def fast(index: int) -> dict[str, Any]:
            started = time.perf_counter_ns()
            response = await client.post(
                "/chat/query",
                headers=headers[index + 1],
                json={"query": FAST_QUERIES[index], "response_mode": "fast"},
            )
            wall_ms = (time.perf_counter_ns() - started) / 1_000_000
            response.raise_for_status()
            body = response.json()
            return {
                "user_index": index + 2,
                "wall_ms": wall_ms,
                "api_total_ms": body["timings_ms"].get("api_total_ms"),
                "embedding_ms": body["timings_ms"].get("embedding_ms"),
                "qdrant_ms": body["timings_ms"].get("qdrant_ms"),
                "citation_count": len(body["citations"]),
                "target_met": body["target_met"],
                "status_code": response.status_code,
            }

        fast_records = await asyncio.gather(*(fast(index) for index in range(3)))

        while True:
            status_response = await client.get(f"/jobs/{job_id}", headers=headers[0])
            status_response.raise_for_status()
            job = status_response.json()
            if job["status"] in {"succeeded", "failed", "cancelled"}:
                break
            await asyncio.sleep(1)
        await event_task
        sampling_done.set()
        await resource_task
        e2e_ms = (time.perf_counter_ns() - scenario_started_ns) / 1_000_000
        result = job.get("result") or {}
        rates = token_rates(result.get("pipeline_metrics", []))
        first_token_times = metric_values(
            result.get("pipeline_metrics", []), "time_to_first_response_token_ms"
        )
        answer = str(result.get("answer") or "")
        fast_walls = [float(item["wall_ms"]) for item in fast_records]
        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "base_url": args.base_url,
            "scenario": "one_deep_three_fast",
            "cohort": cohort,
            "credentials_recorded": False,
            "response_text_recorded": False,
            "deep": {
                "job_id": job_id,
                "enqueue_http_ms": enqueue_ms,
                "first_durable_progress": first_progress,
                "terminal_status": job["status"],
                "progress": job["progress"],
                "attempt_count": job["attempt_count"],
                "created_at": job["created_at"],
                "started_at": job["started_at"],
                "completed_at": job["completed_at"],
                "end_to_end_wall_ms": e2e_ms,
                "workflow_total_ms": (result.get("timings_ms") or {}).get(
                    "workflow_total_ms"
                ),
                "citation_count": len(result.get("citations") or []),
                "ollama_token_rates": rates,
                "ollama_time_to_first_response_token_ms": first_token_times,
                "answer_quality_checks": {
                    "has_structured_heading": "## " in answer,
                    "has_direct_answer_heading": "## Direct answer" in answer,
                    "has_legal_basis_heading": any(
                        heading in answer
                        for heading in (
                            "## Why this is the legal position",
                            "## Verified legal basis",
                        )
                    ),
                    "has_source_reference": "[Source " in answer,
                    "mentions_rag": "rag" in answer.casefold(),
                    "mentions_chunk": "chunk" in answer.casefold(),
                    "has_professional_disclaimer": "Legal decision-support information" in answer,
                },
                "events_seen": events_seen,
            },
            "fast": {
                "records": fast_records,
                "summary_wall_ms": {
                    "min": min(fast_walls),
                    "mean": statistics.fmean(fast_walls),
                    "p95": percentile(fast_walls, 0.95),
                    "max": max(fast_walls),
                },
            },
            "resource_samples": resource_samples,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=420)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    report = asyncio.run(run(arguments))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
