"""Liveness must never touch a dependency; readiness must never lie about one."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.services import health


async def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_liveness_answers_without_touching_dependencies(monkeypatch) -> None:
    """Liveness answers even when every dependency is unreachable."""
    from main import app

    async def explode() -> dict:
        raise AssertionError("liveness must not probe dependencies")

    monkeypatch.setattr(health, "_probe_database", explode)
    monkeypatch.setattr(health, "_probe_qdrant", explode)
    monkeypatch.setattr(health, "_probe_ollama", explode)

    async with await _client(app) as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "alive"
    assert response.headers["Cache-Control"] == "no-store"


async def test_readiness_reports_ready_when_every_dependency_answers(monkeypatch) -> None:
    from main import app

    async def ok_database() -> dict:
        return {}

    async def ok_qdrant() -> dict:
        return {"collections": 3}

    async def ok_ollama() -> dict:
        return {"model": "test-model"}

    monkeypatch.setattr(health, "_probe_database", ok_database)
    monkeypatch.setattr(health, "_probe_qdrant", ok_qdrant)
    monkeypatch.setattr(health, "_probe_ollama", ok_ollama)

    async with await _client(app) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["dependencies"]["qdrant"]["collections"] == 3
    assert payload["dependencies"]["ollama"]["model"] == "test-model"
    assert set(payload["inference"]) == {"embedding", "reranking"}


async def test_readiness_is_degraded_and_503_when_a_dependency_fails(monkeypatch) -> None:
    """The old /health returned 200 while Qdrant was unreachable."""
    from main import app

    async def ok() -> dict:
        return {}

    async def unreachable() -> dict:
        raise ConnectionRefusedError("qdrant is down")

    monkeypatch.setattr(health, "_probe_database", ok)
    monkeypatch.setattr(health, "_probe_qdrant", unreachable)
    monkeypatch.setattr(health, "_probe_ollama", ok)

    async with await _client(app) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["dependencies"]["qdrant"]["status"] == "unavailable"
    assert payload["dependencies"]["qdrant"]["error_type"] == "ConnectionRefusedError"
    assert payload["dependencies"]["database"]["status"] == "ready"


async def test_readiness_never_leaks_a_connection_string(monkeypatch) -> None:
    """Probe messages can carry credentials; only the error type is exposed."""
    from main import app

    async def ok() -> dict:
        return {}

    async def leaky() -> dict:
        raise RuntimeError("postgresql://legal_rag:sup3rs3cret@db:5432/legal_rag refused")

    monkeypatch.setattr(health, "_probe_database", leaky)
    monkeypatch.setattr(health, "_probe_qdrant", ok)
    monkeypatch.setattr(health, "_probe_ollama", ok)

    async with await _client(app) as client:
        response = await client.get("/health/ready")

    assert "sup3rs3cret" not in response.text
    assert response.json()["dependencies"]["database"]["error_type"] == "RuntimeError"


async def test_a_slow_dependency_does_not_hang_readiness(monkeypatch) -> None:
    import asyncio

    from main import app

    async def ok() -> dict:
        return {}

    async def never() -> dict:
        await asyncio.sleep(30)
        return {}

    monkeypatch.setattr(health, "PROBE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(health, "_probe_database", ok)
    monkeypatch.setattr(health, "_probe_qdrant", never)
    monkeypatch.setattr(health, "_probe_ollama", ok)

    async with await _client(app) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["dependencies"]["qdrant"]["error_type"] == "TimeoutError"


def test_accelerated_inference_assertion_is_a_no_op_by_default(monkeypatch) -> None:
    monkeypatch.setattr(health.settings, "expect_accelerated_inference", False)
    monkeypatch.setattr(health, "inference_devices", lambda: {"embedding": "cpu", "reranking": "cpu"})

    health.assert_accelerated_inference()  # must not raise


def test_accelerated_inference_assertion_fails_boot_on_cpu(monkeypatch) -> None:
    """A container built from the CPU torch wheel must not start silently."""
    monkeypatch.setattr(health.settings, "expect_accelerated_inference", True)
    monkeypatch.setattr(health, "inference_devices", lambda: {"embedding": "cpu", "reranking": "cpu"})

    with pytest.raises(RuntimeError, match="embedding resolved to cpu"):
        health.assert_accelerated_inference()


def test_accelerated_inference_assertion_passes_on_mps(monkeypatch) -> None:
    monkeypatch.setattr(health.settings, "expect_accelerated_inference", True)
    monkeypatch.setattr(health, "inference_devices", lambda: {"embedding": "mps", "reranking": "mps"})

    health.assert_accelerated_inference()  # must not raise
