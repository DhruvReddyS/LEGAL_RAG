"""One warm-up call does not warm the encoder.

Measured on an Apple M5 Pro, 8 October 2026, with a freshly loaded BGE-M3:
a short query encodes in 286 ms at the median, 73 ms after another seven
calls, and 33 ms after seven more. The curve is not about the query -- 6-token
and 96-token inputs converge together, and in the same pass a 20-token query
cost 70 ms while a 32-token one cost 614 ms -- so it is Metal kernel
compilation and allocator warming amortised over the first calls, not
anything per-shape.

Production warmed with a single call, which left the next dozen real queries
paying 70-680 ms each. The Fast baseline shows it directly: the first query
after a restart spent 682 ms in the embedder, and 0 ms once cached.

The warm-up therefore encodes until the model stops getting faster. These
tests pin the loop's shape rather than a timing, because a timing assertion
would be a flake on any other host.
"""

from __future__ import annotations

import pytest

from app.services.retrieval import HybridRetrievalService


class _CountingService(HybridRetrievalService):
    """Counts encodes and returns a controllable timing curve."""

    def __init__(self, durations: list[float]) -> None:
        # Deliberately skips HybridRetrievalService.__init__: it builds a
        # Qdrant client, two thread pools and an embedder, none of which this
        # test exercises.
        self._durations = list(durations)
        self.encoded: list[str] = []

    async def embed_documents(self, texts, *, batch_size=8):
        self.encoded.extend(texts)
        if self._durations:
            await _advance(self._durations.pop(0))
        return [object() for _ in texts]


_CLOCK = {"now": 0.0}


async def _advance(seconds: float) -> None:
    _CLOCK["now"] += seconds


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    _CLOCK["now"] = 0.0
    monkeypatch.setattr("app.services.retrieval.perf_counter", lambda: _CLOCK["now"])
    yield


@pytest.mark.asyncio
async def test_it_keeps_encoding_while_the_model_is_still_getting_faster() -> None:
    """A single call is not enough, and the loop must notice that."""
    # Each call twice as fast as the last: never converges inside the bound.
    service = _CountingService([1.0, 0.5, 0.25, 0.125, 0.06, 0.03, 0.015, 0.007] + [0.003] * 40)
    await service.warmup()
    assert len(service.encoded) > 1, "one encode leaves the first real queries cold"
    assert len(service.encoded) <= HybridRetrievalService.WARMUP_MAX_ENCODES


@pytest.mark.asyncio
async def test_it_stops_once_two_consecutive_calls_are_flat() -> None:
    """Boot time is not free, so the loop must not run to its bound.

    Two flat calls rather than one, because the measured curve is noisy
    enough that a single slower call mid-descent would stop it early.
    """
    service = _CountingService([0.30, 0.08, 0.033, 0.033, 0.033, 0.033, 0.033])
    await service.warmup()
    assert len(service.encoded) < HybridRetrievalService.WARMUP_MAX_ENCODES
    assert len(service.encoded) >= 3


@pytest.mark.asyncio
async def test_the_loop_is_bounded_even_if_the_timings_never_settle() -> None:
    """Boot cannot be held open by a host that keeps improving.

    A 20% improvement on every call never satisfies the convergence test,
    so only the call bound stops it.
    """
    service = _CountingService([1.0 * 0.8**index for index in range(200)])
    await service.warmup()
    assert len(service.encoded) == HybridRetrievalService.WARMUP_MAX_ENCODES


@pytest.mark.asyncio
async def test_a_diminishing_curve_settles_well_inside_the_bound() -> None:
    """The real curve is harmonic-ish, and it must not run to the bound.

    Measured: 286 ms, then 73 ms, then 33 ms. Once each call improves by
    less than the convergence ratio twice over, there is nothing left to
    warm and the remaining encodes would be boot time spent for nothing.
    """
    service = _CountingService([1.0 / (index + 1) for index in range(200)])
    await service.warmup()
    assert 3 <= len(service.encoded) < HybridRetrievalService.WARMUP_MAX_ENCODES


@pytest.mark.asyncio
async def test_every_warmup_input_is_distinct() -> None:
    """An identical input could be served from a cache instead of the model.

    That would flatten the curve immediately while warming nothing, and the
    loop would stop at two calls believing it was done.
    """
    service = _CountingService([1.0 * 0.8**index for index in range(200)])
    await service.warmup()
    assert len(set(service.encoded)) == len(service.encoded)


@pytest.mark.asyncio
async def test_the_inputs_vary_in_length_rather_than_repeating_one_shape() -> None:
    assert len(HybridRetrievalService.WARMUP_TEXTS) >= 3
    lengths = {len(text.split()) for text in HybridRetrievalService.WARMUP_TEXTS}
    assert len(lengths) >= 3, "warming one shape is not warming the encoder"
