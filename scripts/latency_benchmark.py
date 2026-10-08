#!/usr/bin/env python3
"""End-to-end Fast and Deep latency and answer-quality benchmark.

One harness for both modes over one versioned query set, through the real HTTP
path: Fast synchronously on /chat/query, Deep as a durable job on
/jobs/deep-review with its event stream consumed so time-to-first-output is
measured rather than assumed.

Latency on this pipeline is only meaningful next to the answer it produced --
reasoning spends most of a Deep run decoding claims, so anything that makes it
faster makes the answer shorter. Every record therefore carries the citation
count, the verified-claim counts, the evidence strength and the answer, so a
change that bought speed by dropping substance is visible rather than inferred.

The report never contains a password. It does contain answers and corpus
excerpts, which are public legal text, because the quality comparison is the
point.

Usage:
    export LEGAL_RAG_BENCHMARK_PASSWORD='...'
    python scripts/latency_benchmark.py --label baseline --mode both
    python scripts/latency_benchmark.py --label baseline --mode fast --repeats 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "evidence" / "latency"

# Version this set, never edit an entry in place. A before/after comparison is
# only valid across the same QUERY_SET_VERSION.
QUERY_SET_VERSION = "latency-v1"

# Chosen to exercise the behaviours the acceptance criteria protect, not to
# flatter the timings:
#   q01-q04  statute and procedure questions the corpus demonstrably covers
#   q05      a lay-worded question whose statutory vocabulary differs entirely
#   q06      a police-role question, so role profiles are on the measured path
#   q07      contract law, which is absent from the corpus: the expected
#            outcome is abstention, and an abstention that gets faster by
#            abstaining more often is a regression, not a win
QUERY_SET: list[dict[str, str]] = [
    {"id": "q01", "role": "citizen", "query": "When can the police arrest someone without a warrant?"},
    {"id": "q02", "role": "citizen", "query": "What are the rights of a person who has been arrested?"},
    {"id": "q03", "role": "citizen", "query": "Is registration of an FIR mandatory when the information discloses a cognizable offence?"},
    {"id": "q04", "role": "citizen", "query": "Explain the scope of Article 14 equality before law."},
    {"id": "q05", "role": "citizen", "query": "The shop refused to replace my phone that stopped working in the warranty period. What can I do?"},
    {"id": "q06", "role": "police", "query": "How must chain of custody be maintained for seized material?"},
    {"id": "q07", "role": "citizen", "query": "What are the essential elements of a valid contract?"},
]

# What invalidates a run is *active* paging, not the cumulative swap figure.
# macOS never returns swap once it has been allocated, so a host that paged
# during an ingestion hours ago still reports 8 GB in use while sitting idle.
# The rate is what costs a measurement: the handoff's "swaps heavily" state
# pages continuously, an idle host pages not at all.
MAX_SWAPOUT_PAGES_PER_SECOND = 64
SWAP_RATE_SAMPLE_SECONDS = 3.0

# Normalised load average above which another task is competing for the CPU.
# One Deep run is a single serialised generation, so a quiet host sits well
# under this.
MAX_LOAD_PER_CPU_FOR_VALID_RUN = 0.75

# Process-name fragments that mean another heavy task holds the machine.
BUSY_PROCESS_MARKERS = (
    "run_rebuild",
    "rebuild_until_done",
    "promote_candidates",
    "app.ingestion.pipeline",
    "ingestion_progress",
    "corpus_reports",
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


def summarise(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"count": 0, "min": None, "p50": None, "p95": None, "max": None, "mean": None}
    return {
        "count": len(values),
        "min": round(min(values), 2),
        "p50": round(percentile(values, 0.50) or 0.0, 2),
        "p95": round(percentile(values, 0.95) or 0.0, 2),
        "max": round(max(values), 2),
        "mean": round(sum(values) / len(values), 2),
    }


def _command(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=15, check=False).stdout.strip()
    except Exception as exc:  # noqa: BLE001 - environment capture must not fail a run
        return f"unavailable:{type(exc).__name__}"


def swap_used_bytes() -> int | None:
    """Cumulative swap allocated. Informational only -- see the note above."""
    # "total = 4096.00M  used = 1234.56M  free = 2861.44M  (encrypted)"
    parts = _command(["sysctl", "-n", "vm.swapusage"]).split()
    for index, token in enumerate(parts):
        if token == "used" and index + 2 < len(parts):
            value = parts[index + 2]
            try:
                number = float(value.rstrip("MG"))
            except ValueError:
                return None
            return int(number * (1024**3 if value.endswith("G") else 1024**2))
    return None


def _vm_stat_counter(name: str) -> int | None:
    for line in _command(["vm_stat"]).splitlines():
        if line.startswith(name):
            try:
                return int(line.split(":", 1)[1].strip().rstrip("."))
            except (IndexError, ValueError):
                return None
    return None


def swapout_rate_pages_per_second(seconds: float = SWAP_RATE_SAMPLE_SECONDS) -> float | None:
    """Pages written to swap per second, sampled over a short window.

    This is the measurement-validity test the handoff asks for. A host under
    an ingestion pages continuously; an idle host returns 0.0 here even when
    it reports gigabytes of cumulative swap.
    """
    first = _vm_stat_counter("Swapouts")
    if first is None:
        return None
    time.sleep(seconds)
    second = _vm_stat_counter("Swapouts")
    if second is None:
        return None
    return round(max(0, second - first) / seconds, 2)


def busy_processes() -> list[str]:
    raw = _command(["ps", "-Ao", "command="])
    found: list[str] = []
    for line in raw.splitlines():
        for marker in BUSY_PROCESS_MARKERS:
            if marker in line and "latency_benchmark" not in line:
                found.append(marker)
    return sorted(set(found))


async def capture_environment(client: httpx.AsyncClient, base_url: str) -> dict[str, Any]:
    environment: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _command(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
        "git_dirty_paths": _command(["git", "-C", str(ROOT), "status", "--porcelain"]).splitlines(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
        "load_average": list(os.getloadavg()),
        "swap_used_bytes": swap_used_bytes(),
        "swapout_pages_per_second": swapout_rate_pages_per_second(),
        "busy_process_markers": busy_processes(),
        "base_url": base_url,
    }
    try:
        ready = await client.get("/health/ready")
        environment["health_ready"] = ready.json()
    except Exception as exc:  # noqa: BLE001
        environment["health_ready_error"] = type(exc).__name__
    async with httpx.AsyncClient(timeout=15) as plain:
        try:
            info = await plain.get("http://127.0.0.1:11434/api/ps")
            environment["ollama_resident"] = [
                {
                    "name": model.get("name"),
                    "size": model.get("size"),
                    "size_vram": model.get("size_vram"),
                    "context_length": model.get("context_length"),
                }
                for model in info.json().get("models", [])
            ]
        except Exception as exc:  # noqa: BLE001
            environment["ollama_error"] = type(exc).__name__
        collection = os.environ.get("QDRANT_GLOBAL_COLLECTION") or _env_file_value("QDRANT_GLOBAL_COLLECTION")
        environment["qdrant_collection"] = collection
        if collection:
            try:
                stats = await plain.get(f"http://127.0.0.1:6333/collections/{collection}")
                result = stats.json().get("result") or {}
                environment["qdrant_points"] = result.get("points_count")
                environment["qdrant_status"] = result.get("status")
            except Exception as exc:  # noqa: BLE001
                environment["qdrant_error"] = type(exc).__name__
    return environment


def _env_file_value(key: str) -> str | None:
    path = ROOT / ".env"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


def stage_breakdown(pipeline_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-stage wall time and LLM accounting, summed across retries."""
    stages: dict[str, float] = {}
    llm_calls = 0
    prompt_tokens = 0
    output_tokens = 0
    llm_ms = 0.0
    for metric in pipeline_metrics or []:
        stage = str(metric.get("stage"))
        if stage == "workflow_total":
            continue
        stages[stage] = round(stages.get(stage, 0.0) + float(metric.get("duration_ms") or 0.0), 2)
        for call in metric.get("llm_calls") or []:
            llm_calls += 1
            prompt_tokens += int(call.get("response_prompt_eval_count") or 0)
            output_tokens += int(call.get("response_eval_count") or 0)
            llm_ms += float(call.get("duration_ms") or 0.0)
    return {
        "stages_ms": stages,
        "llm_call_count": llm_calls,
        "llm_prompt_tokens": prompt_tokens,
        "llm_output_tokens": output_tokens,
        "llm_total_ms": round(llm_ms, 2),
    }


def answer_quality(body: dict[str, Any]) -> dict[str, Any]:
    """Quality fields that must not regress when latency improves."""
    answer = str(body.get("answer") or "")
    citations = body.get("citations") or []
    trace = body.get("agent_trace") or []
    verification = next(
        (event.get("details") or {} for event in trace if event.get("node") == "verification"),
        {},
    )
    return {
        "answer_words": len(answer.split()),
        "answer_characters": len(answer),
        "abstained": answer.strip().startswith("Insufficient") or body.get("evidence_strength") == "insufficient",
        "citation_count": len(citations),
        "distinct_source_titles": len({str(citation.get("title")) for citation in citations}),
        "distinct_source_types": len({str(citation.get("source_type")) for citation in citations}),
        "citations_with_section": sum(1 for citation in citations if citation.get("section")),
        "citations_with_url": sum(1 for citation in citations if citation.get("source_url")),
        "verified_citations": sum(1 for citation in citations if citation.get("verification_status") == "verified"),
        "repeal_labelled_citations": sum(
            1 for citation in citations if citation.get("repeal_label") not in {None, "", "in_force"}
        ),
        "confidence_score": body.get("confidence_score"),
        "evidence_strength": body.get("evidence_strength"),
        "verification_score": verification.get("score"),
        "verification_claims": verification.get("claims"),
        "verification_unsupported": verification.get("unsupported"),
        "verification_unadjudicated": verification.get("unadjudicated"),
        "answer": answer,
    }


async def _job_queue_depth() -> int:
    """How many jobs are queued or running anywhere on this deployment.

    A Deep measurement is only its own cost if nothing else is in front of it.
    The Fast lane auto-escalates a low-confidence answer into a Deep job, so a
    Fast phase leaves work behind, and a Deep run started straight afterwards
    measures the queue rather than the pipeline -- observed once: the Deep
    warm-up sat for six minutes behind three escalated jobs.
    """
    sys.path.insert(0, str(ROOT / "backend"))
    from sqlalchemy import func, select

    from app.core.database import AsyncSessionLocal
    from app.models import Job
    from app.models.enums import JobStatus

    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
            )
            or 0
        )


async def drain_benchmark_jobs(
    client: httpx.AsyncClient,
    headers_by_role: dict[str, dict[str, str]],
    *,
    timeout_s: float = 900.0,
) -> dict[str, Any]:
    """Cancel the benchmark cohort's outstanding jobs and wait for an idle queue."""
    cancelled = 0
    for headers in headers_by_role.values():
        try:
            listing = await client.get("/jobs", headers=headers)
            listing.raise_for_status()
        except Exception:  # noqa: BLE001 - cleanup is best effort
            continue
        for job in listing.json().get("items", []):
            if job.get("status") in {"queued", "running"}:
                try:
                    await client.post(f"/jobs/{job['id']}/cancel", headers=headers)
                    cancelled += 1
                except Exception:  # noqa: BLE001
                    pass
    deadline = time.monotonic() + timeout_s
    depth = await _job_queue_depth()
    while depth and time.monotonic() < deadline:
        await asyncio.sleep(2)
        depth = await _job_queue_depth()
    return {"cancelled_jobs": cancelled, "queue_depth_after_drain": depth}


async def _provision_professional(email: str, name: str, role: str, password: str) -> None:
    """Create a police or advocate benchmark account.

    `/auth/register` refuses any role but citizen on purpose -- professional
    accounts are provisioned by an administrator -- so the benchmark creates
    its own through the same service the admin tool uses rather than relaxing
    that rule. The account is a per-run fixture; the role matters because role
    profiles and the specialist-agent selection sit on the measured path.
    """
    sys.path.insert(0, str(ROOT / "backend"))
    from app.core.database import AsyncSessionLocal
    from app.models.enums import UserRole
    from app.schemas.auth import RegisterRequest
    from app.services.auth import create_user, get_user_by_email

    registration = RegisterRequest(name=name, email=email, password=password, role=UserRole(role))
    async with AsyncSessionLocal() as session:
        if await get_user_by_email(session, str(registration.email)) is not None:
            return
        await create_user(session, registration)
        await session.commit()


async def register(client: httpx.AsyncClient, cohort: str, role: str, password: str) -> dict[str, str]:
    email = f"latency-bench-{cohort}-{role}@example.com"
    name = f"Latency Benchmark {role}"
    if role == "citizen":
        response = await client.post(
            "/auth/register",
            json={"name": name, "email": email, "password": password, "role": role},
        )
        response.raise_for_status()
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    await _provision_professional(email, name, role, password)
    login = await client.post("/auth/login", json={"email": email, "password": password})
    login.raise_for_status()
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def run_fast(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    item: dict[str, str],
    repeat: int,
) -> dict[str, Any]:
    started = time.perf_counter_ns()
    response = await client.post(
        "/chat/query",
        headers=headers,
        json={"query": item["query"], "response_mode": "fast"},
    )
    wall_ms = (time.perf_counter_ns() - started) / 1_000_000
    response.raise_for_status()
    body = response.json()
    timings = body.get("timings_ms") or {}
    record = {
        "mode": "fast",
        "query_id": item["id"],
        "role": item["role"],
        "repeat": repeat,
        "wall_ms": round(wall_ms, 2),
        # Fast returns one complete response, so there is nothing useful
        # before the end of the request. Recorded explicitly rather than
        # omitted, so the Deep comparison is like for like.
        "time_to_first_useful_output_ms": round(wall_ms, 2),
        "timings_ms": timings,
        "selected_mode": body.get("response_mode"),
        "target_met": body.get("target_met"),
        "latency_target_ms": body.get("latency_target_ms"),
        "embedding_cache_hit": timings.get("embedding_cache_hit"),
        **stage_breakdown(body.get("pipeline_metrics") or []),
        **answer_quality(body),
    }
    return record


async def run_deep(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    item: dict[str, str],
    repeat: int,
    poll_interval_s: float,
) -> dict[str, Any]:
    enqueue_started = time.perf_counter_ns()
    enqueue = await client.post(
        "/jobs/deep-review",
        headers={**headers, "Idempotency-Key": f"lat-{uuid.uuid4().hex[:20]}"},
        json={"query": item["query"]},
    )
    enqueue.raise_for_status()
    enqueue_ms = (time.perf_counter_ns() - enqueue_started) / 1_000_000
    job_id = str(enqueue.json()["id"])

    timeline: list[dict[str, Any]] = []
    first_progress_ms: float | None = None
    first_useful_ms: float | None = None
    stream_finished = asyncio.Event()

    async def consume_events() -> None:
        nonlocal first_progress_ms, first_useful_ms
        try:
            async with client.stream("GET", f"/jobs/{job_id}/events", headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    offset_ms = (time.perf_counter_ns() - enqueue_started) / 1_000_000
                    timeline.append(
                        {
                            "event_type": event.get("event_type"),
                            "stage": event.get("stage"),
                            "progress": event.get("progress"),
                            "offset_ms": round(offset_ms, 2),
                        }
                    )
                    if first_progress_ms is None and event.get("stage") not in {None, "queued"}:
                        first_progress_ms = offset_ms
                    # Useful output means source-backed content a reader can
                    # act on, not a progress label. A citation or an answer
                    # chunk is the first thing that qualifies.
                    if first_useful_ms is None and event.get("event_type") in {"citation", "answer_chunk"}:
                        first_useful_ms = offset_ms
        except Exception as exc:  # noqa: BLE001 - a lost stream must not lose the run
            timeline.append({"stream_error": type(exc).__name__})
        finally:
            stream_finished.set()

    event_task = asyncio.create_task(consume_events())
    job: dict[str, Any] = {}
    while True:
        status_response = await client.get(f"/jobs/{job_id}", headers=headers)
        status_response.raise_for_status()
        job = status_response.json()
        if job.get("status") in {"succeeded", "failed", "cancelled"}:
            break
        await asyncio.sleep(poll_interval_s)
    wall_ms = (time.perf_counter_ns() - enqueue_started) / 1_000_000
    with_timeout = asyncio.wait_for(stream_finished.wait(), timeout=10)
    try:
        await with_timeout
    except TimeoutError:
        pass
    event_task.cancel()

    result = job.get("result") or {}
    record = {
        "mode": "deep",
        "query_id": item["id"],
        "role": item["role"],
        "repeat": repeat,
        "job_status": job.get("status"),
        "attempt_count": job.get("attempt_count"),
        "wall_ms": round(wall_ms, 2),
        "enqueue_ms": round(enqueue_ms, 2),
        "time_to_first_progress_ms": round(first_progress_ms, 2) if first_progress_ms is not None else None,
        "time_to_first_useful_output_ms": round(first_useful_ms, 2) if first_useful_ms is not None else None,
        "timings_ms": result.get("timings_ms") or {},
        "event_timeline": timeline,
        **stage_breakdown(result.get("pipeline_metrics") or []),
        **answer_quality(result),
    }
    return record


async def run(args: argparse.Namespace) -> dict[str, Any]:
    password = os.environ.get("LEGAL_RAG_BENCHMARK_PASSWORD")
    if not password:
        raise SystemExit("Set LEGAL_RAG_BENCHMARK_PASSWORD; it is never written to the report.")
    cohort = uuid.uuid4().hex[:12]
    timeout = httpx.Timeout(args.timeout, connect=10)
    items = [item for item in QUERY_SET if args.only is None or item["id"] in args.only]
    if not items:
        raise SystemExit("No query matched --only")

    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout) as client:
        environment = await capture_environment(client, args.base_url)
        guard: list[str] = []
        if environment.get("busy_process_markers"):
            guard.append(f"busy processes: {environment['busy_process_markers']}")
        swapout_rate = environment.get("swapout_pages_per_second")
        if isinstance(swapout_rate, (int, float)) and swapout_rate > MAX_SWAPOUT_PAGES_PER_SECOND:
            guard.append(f"host is paging at {swapout_rate} swapouts/s")
        cpu_count = environment.get("cpu_count") or 1
        load_1m = (environment.get("load_average") or [0.0])[0]
        if load_1m / cpu_count > MAX_LOAD_PER_CPU_FOR_VALID_RUN:
            guard.append(f"1-minute load average is {load_1m:.2f} across {cpu_count} CPUs")
        if guard and not args.allow_busy_machine:
            raise SystemExit(
                "Refusing to measure: " + "; ".join(guard)
                + ". A run taken on a loaded machine is not comparable to an idle one. "
                "Pass --allow-busy-machine only to record a deliberately loaded scenario."
            )
        queue_depth = await _job_queue_depth()
        if queue_depth and not args.allow_busy_machine:
            raise SystemExit(
                f"Refusing to measure: {queue_depth} job(s) are queued or running. "
                "A Deep measurement taken behind another job measures the queue, not "
                "the pipeline. Wait for the queue to drain, or cancel the jobs."
            )
        environment["initial_job_queue_depth"] = queue_depth
        environment["validity_warnings"] = guard

        roles = sorted({item["role"] for item in items})
        headers_by_role = {role: await register(client, cohort, role, password) for role in roles}

        records: list[dict[str, Any]] = []
        modes = ["fast", "deep"] if args.mode == "both" else [args.mode]

        for mode in modes:
            # One warm-up per mode, discarded. The first request of a process
            # pays for the embedding cache being empty and, in Deep, for the
            # reasoning model not being resident.
            if args.warmup:
                warm = items[0]
                print(f"[{mode}] warm-up ({warm['id']}) ...", flush=True)
                if mode == "fast":
                    await run_fast(client, headers_by_role[warm["role"]], warm, repeat=-1)
                else:
                    await run_deep(client, headers_by_role[warm["role"]], warm, -1, args.poll_interval)
            for repeat in range(args.repeats):
                for item in items:
                    label = f"[{mode}] {item['id']} r{repeat}"
                    print(f"{label} ...", end="", flush=True)
                    if mode == "fast":
                        record = await run_fast(client, headers_by_role[item["role"]], item, repeat)
                    else:
                        record = await run_deep(client, headers_by_role[item["role"]], item, repeat, args.poll_interval)
                    records.append(record)
                    print(
                        f" {record['wall_ms'] / 1000:7.2f} s  "
                        f"{record['citation_count']} cites  "
                        f"{record['answer_words']:>4} words  "
                        f"{record['evidence_strength']}",
                        flush=True,
                    )
            if mode == "fast":
                # The Fast lane enqueues a Deep job whenever its confidence
                # falls below the escalation threshold. Left alone, that work
                # runs during the next phase and corrupts it.
                drained = await drain_benchmark_jobs(client, headers_by_role)
                print(f"[fast] drained escalated jobs: {drained}", flush=True)
                environment["fast_phase_drain"] = drained

    summary: dict[str, Any] = {}
    for mode in sorted({record["mode"] for record in records}):
        subset = [record for record in records if record["mode"] == mode]
        summary[mode] = {
            "end_to_end_ms": summarise([float(record["wall_ms"]) for record in subset]),
            "time_to_first_useful_output_ms": summarise(
                [
                    float(record["time_to_first_useful_output_ms"])
                    for record in subset
                    if record.get("time_to_first_useful_output_ms") is not None
                ]
            ),
            "stage_p50_ms": {
                stage: round(percentile(values, 0.50) or 0.0, 2)
                for stage, values in sorted(_stage_values(subset).items())
            },
            "stage_p95_ms": {
                stage: round(percentile(values, 0.95) or 0.0, 2)
                for stage, values in sorted(_stage_values(subset).items())
            },
            "llm_calls_per_query": summarise([float(record["llm_call_count"]) for record in subset]),
            "llm_output_tokens_per_query": summarise([float(record["llm_output_tokens"]) for record in subset]),
            "llm_prompt_tokens_per_query": summarise([float(record["llm_prompt_tokens"]) for record in subset]),
            "quality": {
                "citations_per_query": summarise([float(record["citation_count"]) for record in subset]),
                "distinct_source_titles_per_query": summarise(
                    [float(record["distinct_source_titles"]) for record in subset]
                ),
                "answer_words": summarise([float(record["answer_words"]) for record in subset]),
                "abstention_rate": round(sum(bool(record["abstained"]) for record in subset) / len(subset), 4),
                "verification_score": summarise(
                    [
                        float(record["verification_score"])
                        for record in subset
                        if record.get("verification_score") is not None
                    ]
                ),
                "unsupported_claims_per_query": summarise(
                    [
                        float(record["verification_unsupported"])
                        for record in subset
                        if record.get("verification_unsupported") is not None
                    ]
                ),
            },
        }

    return {
        "schema_version": 1,
        "label": args.label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query_set_version": QUERY_SET_VERSION,
        "query_set": items,
        "repeats": args.repeats,
        "warmup_discarded": bool(args.warmup),
        "environment": environment,
        "summary": summary,
        "records": records,
    }


def _stage_values(records: list[dict[str, Any]]) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {}
    for record in records:
        for stage, duration in (record.get("stages_ms") or {}).items():
            values.setdefault(stage, []).append(float(duration))
        for stage, duration in (record.get("timings_ms") or {}).items():
            if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                values.setdefault(f"timing:{stage}", []).append(float(duration))
    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--label", required=True, help="Evidence label, for example 'baseline' or 'after'")
    parser.add_argument("--mode", choices=("fast", "deep", "both"), default="both")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--only", nargs="*", help="Query ids to restrict the run to")
    parser.add_argument("--warmup", action="store_true", default=True)
    parser.add_argument("--no-warmup", dest="warmup", action="store_false")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--allow-busy-machine", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if args.output is None:
        args.output = DEFAULT_OUTPUT_DIR / f"{args.mode}-{args.label}.json"
    return args


if __name__ == "__main__":
    arguments = parse_args()
    report = asyncio.run(run(arguments))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nWrote {arguments.output}")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
