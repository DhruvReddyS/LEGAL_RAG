#!/usr/bin/env python3
"""Measure two durable Deep jobs queued behind the single Ollama lane."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx


QUERY = (
    "A complainant reports that police declined to register information alleging a cognizable "
    "offence. Explain the supported procedural options, counterarguments, and limits. Cite only "
    "retrieved sources and abstain where support is absent."
)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def run(args: argparse.Namespace) -> dict:
    password = os.environ.get("LEGAL_RAG_BENCHMARK_PASSWORD")
    if not password:
        raise SystemExit("Set LEGAL_RAG_BENCHMARK_PASSWORD; it is never written to evidence.")
    cohort = uuid.uuid4().hex[:12]
    async with httpx.AsyncClient(
        base_url=args.base_url,
        timeout=httpx.Timeout(args.timeout, connect=10),
    ) as client:
        tokens: list[str] = []
        for index in range(2):
            response = await client.post(
                "/auth/register",
                json={
                    "name": f"Queued Deep User {index + 1}",
                    "email": f"queued-deep-{cohort}-{index + 1}@example.com",
                    "password": password,
                    "role": "citizen",
                },
            )
            response.raise_for_status()
            tokens.append(str(response.json()["access_token"]))

        jobs: list[dict] = []
        for index, token in enumerate(tokens):
            started_ns = time.perf_counter_ns()
            response = await client.post(
                "/jobs/deep-review",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Idempotency-Key": f"queued-{cohort}-{index + 1}",
                },
                json={"query": QUERY},
            )
            enqueue_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
            response.raise_for_status()
            jobs.append(
                {
                    "id": str(response.json()["id"]),
                    "token": token,
                    "enqueue_http_ms": enqueue_ms,
                }
            )

        pending = {job["id"] for job in jobs}
        terminal: dict[str, dict] = {}
        while pending:
            for job in jobs:
                if job["id"] not in pending:
                    continue
                response = await client.get(
                    f"/jobs/{job['id']}",
                    headers={"Authorization": f"Bearer {job['token']}"},
                )
                response.raise_for_status()
                body = response.json()
                if body["status"] in {"succeeded", "failed", "cancelled"}:
                    terminal[job["id"]] = body
                    pending.remove(job["id"])
            if pending:
                await asyncio.sleep(1)

        records: list[dict] = []
        for position, job in enumerate(jobs, 1):
            body = terminal[job["id"]]
            created = parse_timestamp(body["created_at"])
            started = parse_timestamp(body["started_at"])
            completed = parse_timestamp(body["completed_at"])
            result = body.get("result") or {}
            records.append(
                {
                    "position": position,
                    "job_id": job["id"],
                    "status": body["status"],
                    "attempt_count": body["attempt_count"],
                    "enqueue_http_ms": job["enqueue_http_ms"],
                    "queue_wait_ms": (started - created).total_seconds() * 1000,
                    "service_ms": (completed - started).total_seconds() * 1000,
                    "end_to_end_ms": (completed - created).total_seconds() * 1000,
                    "citation_count": len(result.get("citations") or []),
                    "answer_text_recorded": False,
                }
            )
        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scenario": "two_queued_deep_jobs",
            "credentials_recorded": False,
            "records": records,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=720)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    report = asyncio.run(run(arguments))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
