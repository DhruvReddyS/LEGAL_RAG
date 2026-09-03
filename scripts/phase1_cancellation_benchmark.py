#!/usr/bin/env python3
"""Measure live Deep cancellation acknowledgement and post-cancel Ollama availability."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


QUERY = (
    "Analyze procedural remedies, evidentiary weaknesses, counterarguments, and authority limits "
    "where police decline to register information alleging a cognizable offence."
)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    password = os.environ.get("LEGAL_RAG_BENCHMARK_PASSWORD")
    if not password:
        raise SystemExit("Set LEGAL_RAG_BENCHMARK_PASSWORD; it is never recorded.")
    cohort = uuid.uuid4().hex[:12]
    timeout = httpx.Timeout(420, connect=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        registered = await client.post(
            f"{args.base_url}/auth/register",
            json={
                "name": "Phase 1 Cancellation User",
                "email": f"phase1-cancel-{cohort}@example.com",
                "password": password,
                "role": "citizen",
            },
        )
        registered.raise_for_status()
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        enqueue = await client.post(
            f"{args.base_url}/jobs/deep-review",
            headers={**headers, "Idempotency-Key": f"cancel-{cohort}"},
            json={"query": QUERY},
        )
        enqueue.raise_for_status()
        job_id = str(enqueue.json()["id"])
        reasoning_event: dict[str, Any] | None = None
        async with client.stream(
            "GET", f"{args.base_url}/jobs/{job_id}/events", headers=headers
        ) as stream:
            stream.raise_for_status()
            async for line in stream.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if event["stage"] == "reasoning" and event["data"]["transition"] == "started":
                    reasoning_event = {
                        "id": event["id"],
                        "created_at": event["created_at"],
                        "progress": event["progress"],
                    }
                    break

        await asyncio.sleep(args.cancel_delay_seconds)
        cancel_started = time.perf_counter_ns()
        cancelled = await client.post(
            f"{args.base_url}/jobs/{job_id}/cancel", headers=headers
        )
        cancel_http_ms = (time.perf_counter_ns() - cancel_started) / 1_000_000
        cancelled.raise_for_status()
        terminal_started = time.perf_counter_ns()
        while True:
            status = await client.get(f"{args.base_url}/jobs/{job_id}", headers=headers)
            status.raise_for_status()
            job = status.json()
            if job["status"] in {"cancelled", "failed", "succeeded"}:
                break
            await asyncio.sleep(0.05)
        terminal_after_cancel_ms = (time.perf_counter_ns() - terminal_started) / 1_000_000

        probe_started = time.perf_counter_ns()
        probe = await client.post(
            f"{args.ollama_url}/api/generate",
            json={
                "model": args.model,
                "prompt": "Return the single word ready.",
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 1},
            },
        )
        probe_ms = (time.perf_counter_ns() - probe_started) / 1_000_000
        probe.raise_for_status()
        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id,
            "credentials_recorded": False,
            "response_text_recorded": False,
            "cancel_requested_during": "reasoning",
            "cancel_delay_after_reasoning_started_seconds": args.cancel_delay_seconds,
            "reasoning_event": reasoning_event,
            "cancel_http_ms": cancel_http_ms,
            "cancel_response_status": cancelled.json()["status"],
            "terminal_status": job["status"],
            "terminal_after_cancel_ms": terminal_after_cancel_ms,
            "post_cancel_ollama_probe_ms": probe_ms,
            "post_cancel_ollama_probe_done_reason": probe.json().get("done_reason"),
            "post_cancel_ollama_probe_eval_count": probe.json().get("eval_count"),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3-14b-16k:latest")
    parser.add_argument("--cancel-delay-seconds", type=float, default=5.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    report = asyncio.run(run(arguments))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
