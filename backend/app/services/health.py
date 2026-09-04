"""Dependency probes behind the readiness endpoint.

`/health` previously returned a static healthy response without touching any
dependency, so Docker and any load balancer would route traffic to a backend
whose vector store was unreachable. Liveness and readiness are different
questions and now have different endpoints.

Every probe is bounded and never raises: readiness must report a degraded
dependency, not fail to answer.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.qdrant import create_qdrant_client


PROBE_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    ready: bool
    duration_ms: float
    detail: dict[str, Any] = field(default_factory=dict)
    error_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "ready" if self.ready else "unavailable",
            "duration_ms": round(self.duration_ms, 2),
        }
        if self.error_type is not None:
            # The error type is safe to expose; the message may carry a
            # connection string or credential and is deliberately dropped.
            payload["error_type"] = self.error_type
        payload.update(self.detail)
        return payload


async def _timed(name: str, probe) -> DependencyStatus:
    started = perf_counter()
    try:
        detail = await asyncio.wait_for(probe(), timeout=PROBE_TIMEOUT_SECONDS)
        return DependencyStatus(
            name=name,
            ready=True,
            duration_ms=(perf_counter() - started) * 1000,
            detail=detail or {},
        )
    except (Exception, asyncio.TimeoutError) as exc:  # noqa: BLE001 - probes never raise
        return DependencyStatus(
            name=name,
            ready=False,
            duration_ms=(perf_counter() - started) * 1000,
            error_type=type(exc).__name__,
        )


async def _probe_database() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    return {}


async def _probe_qdrant() -> dict[str, Any]:
    client = create_qdrant_client()
    try:
        collections = await client.get_collections()
        return {"collections": len(collections.collections)}
    finally:
        await client.close()


async def _probe_ollama() -> dict[str, Any]:
    base_url = settings.ollama_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_SECONDS) as client:
        response = await client.get(f"{base_url}/api/tags")
        response.raise_for_status()
        names = {
            str(model.get("model") or model.get("name") or "")
            for model in response.json().get("models", [])
        }
    # A reachable Ollama that has not pulled the configured model will fail
    # every generation, so readiness must distinguish the two cases.
    if settings.ollama_model not in names:
        raise RuntimeError("configured model is not present on the Ollama host")
    return {"model": settings.ollama_model}


def inference_devices() -> dict[str, str]:
    """Report the device the embedder and reranker will actually use.

    E-08 and E-15 were unanswerable from the outside because nothing logged
    this. Inside a container built from the CPU torch wheel it resolves to
    "cpu" no matter what the setting says, which is the difference between a
    5-second and a 20-second retrieval stage.
    """
    try:
        from app.ingestion.embedder import resolve_embedding_device

        device = resolve_embedding_device()
    except Exception as exc:  # noqa: BLE001 - never block startup on this
        return {"embedding": f"unresolved:{type(exc).__name__}", "reranking": "unknown"}
    # Both models resolve through the same helper today; report them
    # separately so splitting them later does not silently change meaning.
    return {"embedding": device, "reranking": device}


def assert_accelerated_inference() -> None:
    """Fail startup when acceleration is required but unavailable.

    Opt-in via EXPECT_ACCELERATED_INFERENCE. Without it a misconfigured
    deployment runs correctly but several times slower, which is the failure
    mode that is hardest to notice and easiest to misattribute.
    """
    if not settings.expect_accelerated_inference:
        return
    devices = inference_devices()
    unaccelerated = sorted(
        name for name, device in devices.items() if device not in {"cuda", "mps"}
    )
    if unaccelerated:
        raise RuntimeError(
            "EXPECT_ACCELERATED_INFERENCE is set but "
            + ", ".join(f"{name} resolved to {devices[name]}" for name in unaccelerated)
            + ". Run the backend natively on an Apple Silicon or CUDA host, or unset the flag."
        )


# Below this many billion parameters a model is a small tier: fine for
# classification or routing, not fine for reasoning, verification or response
# generation. The verifier decides whether a claim is entailed by its source,
# and a weaker judge there does not fail loudly -- it approves claims it should
# have refused, which reads downstream as a *higher* verification score.
SMALL_MODEL_PARAMETER_BILLIONS = 8.0

# "qwen3:4b", "phi3:3.8b", "llama3.2:1b" -- the size as tagged by the registry.
_PARAMETER_COUNT = re.compile(r"[:\-](\d+(?:\.\d+)?)\s*b\b", re.IGNORECASE)

# The escape hatch is deliberately verbose. Anyone who needs it is doing
# something the rest of this function argues against, and should have to say so.
ALLOW_SMALL_MODEL_ENV = "ALLOW_SMALL_REASONING_MODEL"


def is_small_tier_model(name: str) -> bool:
    """Whether a model name advertises a parameter count too small to judge.

    A name that states no size is not treated as small: guessing from an
    unlabelled name would block legitimate models, and this check exists to
    catch the deliberate, plausible swap rather than to police naming.
    """
    sizes = [float(match) for match in _PARAMETER_COUNT.findall(name or "")]
    return any(size < SMALL_MODEL_PARAMETER_BILLIONS for size in sizes)


def assert_reasoning_model_tier() -> None:
    """Fail startup when the generation model is too small to verify claims.

    The PRD rule is that the small tier never touches reasoning, verification
    or response generation, and that it is enforced at boot rather than by
    convention. One model currently serves all three roles, so the check is on
    that model.

    It exists because the tempting change is a plausible one: this machine has
    qwen3:4b installed, it decodes roughly three times faster than the 14B, and
    swapping OLLAMA_MODEL to it would look like a latency win. What it would
    actually do is put a weaker judge on claim verification, whose failure mode
    is approving unsupported claims -- which raises the verification score
    while making the answers less trustworthy.
    """
    if os.environ.get(ALLOW_SMALL_MODEL_ENV) == "1":
        return
    model = settings.ollama_model
    if is_small_tier_model(model):
        raise RuntimeError(
            f"OLLAMA_MODEL is {model!r}, which advertises a small parameter "
            "count. This model performs reasoning, claim verification and "
            "response generation, and a weaker judge there approves claims it "
            "should refuse rather than failing visibly. Use the 14B tier, or "
            f"set {ALLOW_SMALL_MODEL_ENV}=1 to override deliberately."
        )


def log_runtime_profile(logger) -> None:
    devices = inference_devices()
    logger.info(
        json.dumps(
            {
                "event": "runtime_profile",
                "embedding_device": devices["embedding"],
                "reranking_device": devices["reranking"],
                "ollama_base_url_host": urlsplit(settings.ollama_base_url).hostname,
                "ollama_model": settings.ollama_model,
                "job_worker_enabled": settings.job_worker_enabled,
            },
            separators=(",", ":"),
        )
    )


async def readiness_report() -> tuple[bool, dict[str, Any]]:
    database, qdrant, ollama = await asyncio.gather(
        _timed("database", _probe_database),
        _timed("qdrant", _probe_qdrant),
        _timed("ollama", _probe_ollama),
    )
    dependencies = [database, qdrant, ollama]
    ready = all(dependency.ready for dependency in dependencies)
    return ready, {
        "status": "ready" if ready else "degraded",
        "api_compatibility": "1",
        "dependencies": {
            dependency.name: dependency.as_dict() for dependency in dependencies
        },
        "inference": inference_devices(),
    }
