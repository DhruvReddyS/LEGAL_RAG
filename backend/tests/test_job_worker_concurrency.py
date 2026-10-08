"""A queued job's retrieval should not wait for the answer ahead of it.

The worker ran one job end to end. Measured with two Deep jobs enqueued back
to back: the first waited 0.3 s and was served in 57.3 s; the second waited
**57.6 s** and was served in 31.9 s. The second job's retrieval had not
started, so the authorities its question reached -- published at 0.57 s for a
single user -- did not reach it for 58 seconds.

This does not parallelise generation and must not. `OllamaClient` holds its
own semaphore at `ollama_generation_concurrency`, and that is the real
constraint: one slot, one 14B model, 14 tokens a second. What overlaps is the
work that needs no model.

These tests pin the loop's shape and the three ways concurrency goes wrong:
work left running at shutdown, a task whose exception nobody retrieves, and a
claim loop that spins instead of waiting.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.job_worker import DurableJobWorker


class _Harness(DurableJobWorker):
    """Drives the real `_run` loop with claims and executions under test control."""

    def __init__(self, *, claims: list[object], concurrency: int, hold: asyncio.Event | None = None):
        # Deliberately skips DurableJobWorker.__init__: it needs a workflow,
        # and none of this exercises one.
        self.workflow = None  # type: ignore[assignment]
        self.poll_interval_seconds = 0.01
        self.concurrency = concurrency
        self._stop = asyncio.Event()
        self._task = None
        self._in_flight = set()
        self._claims = list(claims)
        self._hold = hold
        self.started: list[object] = []
        self.finished: list[object] = []
        self.peak_in_flight = 0

    async def _claim(self):
        if not self._claims:
            return None
        return self._claims.pop(0)

    async def _execute(self, job_id) -> None:  # type: ignore[override]
        self.started.append(job_id)
        self.peak_in_flight = max(self.peak_in_flight, len(self._in_flight))
        if self._hold is not None:
            await self._hold.wait()
        else:
            await asyncio.sleep(0)
        self.finished.append(job_id)


@pytest.mark.asyncio
async def test_a_second_job_starts_while_the_first_is_still_running() -> None:
    """The whole point. With concurrency 1 the second start waits."""
    hold = asyncio.Event()
    worker = _Harness(claims=["a", "b"], concurrency=2, hold=hold)
    runner = asyncio.create_task(worker._run())
    for _ in range(50):
        if len(worker.started) >= 2:
            break
        await asyncio.sleep(0.01)
    assert worker.started == ["a", "b"], "the second job never started while the first ran"
    assert worker.finished == [], "neither job should have finished yet"
    hold.set()
    worker._stop.set()
    await runner


@pytest.mark.asyncio
async def test_concurrency_one_reproduces_the_old_serial_behaviour() -> None:
    """The setting must be able to turn this off exactly."""
    hold = asyncio.Event()
    worker = _Harness(claims=["a", "b"], concurrency=1, hold=hold)
    runner = asyncio.create_task(worker._run())
    for _ in range(20):
        await asyncio.sleep(0.01)
        if worker.started:
            break
    await asyncio.sleep(0.05)
    assert worker.started == ["a"], "a second job started despite concurrency 1"
    hold.set()
    worker._stop.set()
    await runner


@pytest.mark.asyncio
async def test_the_limit_is_never_exceeded() -> None:
    hold = asyncio.Event()
    worker = _Harness(claims=list("abcdef"), concurrency=3, hold=hold)
    runner = asyncio.create_task(worker._run())
    for _ in range(50):
        if len(worker.started) >= 3:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    assert len(worker.started) == 3
    assert worker.peak_in_flight <= 3
    hold.set()
    worker._stop.set()
    await runner


@pytest.mark.asyncio
async def test_nothing_is_left_running_after_a_stop() -> None:
    """`stop()` re-queues what was interrupted, so a leak loses a job quietly."""
    hold = asyncio.Event()
    worker = _Harness(claims=["a", "b"], concurrency=2, hold=hold)
    runner = asyncio.create_task(worker._run())
    for _ in range(50):
        if len(worker.started) >= 2:
            break
        await asyncio.sleep(0.01)
    worker._stop.set()
    await asyncio.wait_for(runner, timeout=2)
    assert worker._in_flight == set(), "in-flight tasks outlived the worker loop"


@pytest.mark.asyncio
async def test_a_task_that_raises_is_reaped_and_named() -> None:
    """An unretrieved task exception is logged by asyncio, detached from its job.

    `_execute` handles its own failures, so anything escaping is a defect and
    must be reported as one rather than surfacing as a bare traceback at
    garbage-collection time.
    """

    class _Failing(_Harness):
        async def _execute(self, job_id) -> None:  # type: ignore[override]
            self.started.append(job_id)
            raise RuntimeError("escaped")

    worker = _Failing(claims=["a"], concurrency=2)
    runner = asyncio.create_task(worker._run())
    for _ in range(50):
        if worker.started:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    worker._stop.set()
    await asyncio.wait_for(runner, timeout=2)
    assert worker._in_flight == set(), "a failed task was never cleared"


@pytest.mark.asyncio
async def test_an_idle_worker_waits_rather_than_spinning() -> None:
    """With nothing to claim the loop must not busy-poll a database."""
    worker = _Harness(claims=[], concurrency=2)
    calls = 0
    original = worker._claim

    async def counting_claim():
        nonlocal calls
        calls += 1
        return await original()

    worker._claim = counting_claim  # type: ignore[assignment]
    runner = asyncio.create_task(worker._run())
    await asyncio.sleep(0.08)
    worker._stop.set()
    await asyncio.wait_for(runner, timeout=2)
    # 0.08 s at a 0.01 s poll interval is at most ~9 polls. A spinning loop
    # would be in the thousands.
    assert calls <= 20, f"claimed {calls} times in 80 ms; the loop is spinning"


def test_the_default_is_one_because_concurrency_measured_worse() -> None:
    """Measured with two users asking *different* questions:

        concurrency 1   user 1  38.4 s     user 2  74.3 s
        concurrency 2   user 1  69.5 s     user 2  74.2 s

    The last user finishes at ~74 s either way -- throughput is the single
    generation slot and that did not change -- while the first asker's answer
    took 81% longer. Two jobs in flight interleave on the generation
    semaphore, turning FIFO into round-robin. For a queue of legal answers
    the first person to ask should be the first person answered.

    An earlier pass appeared to show the opposite because both users were
    given the identical question, so the second job's prefill came from the
    first's cached prefix.
    """
    from app.core.config import settings

    assert settings.job_worker_concurrency == 1
    assert settings.ollama_generation_concurrency == 1
