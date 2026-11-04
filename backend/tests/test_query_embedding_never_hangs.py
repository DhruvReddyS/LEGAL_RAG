"""A query arriving during a model pass must still get its embedding.

The batch task flushed once. A request arriving while the model ran saw that
task still alive and started none, so it waited, with no timeout, until an
unrelated later request happened to start a new flush. On a quiet server that
could be forever.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import pytest

from app.services.retrieval import HybridRetrievalService


@dataclass
class _Embedded:
    dense: list[float]


class _SlowEmbedder:
    def embed_texts(self, texts, *, batch_size):
        time.sleep(0.2)
        return [_Embedded([float(len(text))]) for text in texts]


def _service() -> HybridRetrievalService:
    return HybridRetrievalService(client=object(), embedder=_SlowEmbedder(), reranker=object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_a_query_arriving_during_a_model_pass_is_answered() -> None:
    service = _service()
    first = asyncio.create_task(service.embed_query("a"))
    await asyncio.sleep(0.05)
    second = asyncio.create_task(service.embed_query("bb"))

    assert await asyncio.wait_for(first, timeout=2) == [1.0]
    assert await asyncio.wait_for(second, timeout=2) == [2.0]


@pytest.mark.asyncio
async def test_the_next_query_after_the_queue_drains_is_answered() -> None:
    service = _service()
    assert await asyncio.wait_for(service.embed_query("a"), timeout=2) == [1.0]
    await asyncio.sleep(0.05)
    assert await asyncio.wait_for(service.embed_query("bb"), timeout=2) == [2.0]


@pytest.mark.asyncio
async def test_a_failed_pass_reaches_the_caller_and_the_next_query_still_works() -> None:
    service = _service()
    calls = {"count": 0}

    class _FailsOnce(_SlowEmbedder):
        def embed_texts(self, texts, *, batch_size):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("model unavailable")
            return super().embed_texts(texts, batch_size=batch_size)

    service.embedder = _FailsOnce()  # type: ignore[assignment]
    with pytest.raises(RuntimeError):
        await asyncio.wait_for(service.embed_query("a"), timeout=2)
    assert await asyncio.wait_for(service.embed_query("bb"), timeout=2) == [2.0]
