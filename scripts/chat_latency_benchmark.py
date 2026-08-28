#!/usr/bin/env python3
"""Authenticated latency benchmark for Fast and Deep legal research modes.

Password input is read only from LEGAL_RAG_BENCHMARK_PASSWORD. The report never
contains credentials or response bodies. Use a dedicated non-production user.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


DEFAULT_QUERIES = [
    "Is FIR registration mandatory for a cognizable offence?",
    "What are the conditions for granting bail under criminal procedure?",
    "Explain the scope of Article 14 equality before law.",
    "What are the essential elements of a valid contract?",
    "What legal steps may be considered when a pet dog is missing?",
]


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


async def run(args: argparse.Namespace) -> dict[str, Any]:
    password = os.environ.get("LEGAL_RAG_BENCHMARK_PASSWORD")
    if not password:
        raise SystemExit("Set LEGAL_RAG_BENCHMARK_PASSWORD; it is never written to the report.")
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    timeout = httpx.Timeout(args.timeout)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout, limits=limits) as client:
        login = await client.post("/auth/cookie/login", json={"email": args.email, "password": password})
        login.raise_for_status()

        async def query_once(query: str, measured: bool) -> dict[str, Any] | None:
            started = time.perf_counter()
            response = await client.post(
                "/chat/query",
                json={"query": query, "response_mode": args.mode},
            )
            wall_ms = round((time.perf_counter() - started) * 1000, 2)
            response.raise_for_status()
            if not measured:
                return None
            body = response.json()
            return {
                "query_index": DEFAULT_QUERIES.index(query) + 1 if query in DEFAULT_QUERIES else None,
                "wall_ms": wall_ms,
                "api_total_ms": body["timings_ms"].get("api_total_ms"),
                "timings_ms": body["timings_ms"],
                "target_met": body["target_met"],
                "citation_count": len(body["citations"]),
                "evidence_strength": body["evidence_strength"],
                "response_mode": body["response_mode"],
            }

        for query in DEFAULT_QUERIES[: args.warmup]:
            await query_once(query, False)

        work = [DEFAULT_QUERIES[index % len(DEFAULT_QUERIES)] for index in range(args.runs)]
        records: list[dict[str, Any]] = []
        for offset in range(0, len(work), args.concurrency):
            batch = await asyncio.gather(*(query_once(query, True) for query in work[offset : offset + args.concurrency]))
            records.extend(record for record in batch if record is not None)

    wall = [float(record["wall_ms"]) for record in records]
    stages: dict[str, list[float]] = defaultdict(list)
    for record in records:
        for name, value in record["timings_ms"].items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                stages[name].append(float(value))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "mode": args.mode,
        "runs": len(records),
        "concurrency": args.concurrency,
        "warmup_queries": args.warmup,
        "summary_ms": {
            "min": round(min(wall), 2),
            "mean": round(statistics.fmean(wall), 2),
            "p50": round(percentile(wall, 0.50), 2),
            "p95": round(percentile(wall, 0.95), 2),
            "p99": round(percentile(wall, 0.99), 2),
            "max": round(max(wall), 2),
        },
        "target_met_rate": round(sum(record["target_met"] is True for record in records) / len(records), 4),
        "stage_p95_ms": {name: round(percentile(values, 0.95), 2) for name, values in sorted(stages.items())},
        "records": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark authenticated Fast/Deep chat latency without logging answer text")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", required=True, help="Dedicated benchmark user email")
    parser.add_argument("--mode", choices=("fast", "deep"), default="fast")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.runs < 1 or args.warmup < 0 or args.concurrency < 1:
        parser.error("runs and concurrency must be positive; warmup must be non-negative")
    return args


if __name__ == "__main__":
    arguments = parse_args()
    report = asyncio.run(run(arguments))
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
