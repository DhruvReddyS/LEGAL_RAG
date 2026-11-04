"""A brief database outage must not stop the worker for good."""

from __future__ import annotations

import asyncio

import pytest

from app.services.job_worker import DurableJobWorker


@pytest.mark.asyncio
async def test_a_failed_claim_is_retried() -> None:
    worker = DurableJobWorker(object(), poll_interval_ms=1)  # type: ignore[arg-type]
    calls = {"count": 0}

    async def claim():
        calls["count"] += 1
        if calls["count"] == 1:
            raise ConnectionError("database restarting")
        if calls["count"] >= 3:
            worker._stop.set()
        return None

    worker._claim = claim  # type: ignore[method-assign]
    await asyncio.wait_for(worker._run(), timeout=2)
    assert calls["count"] >= 3
