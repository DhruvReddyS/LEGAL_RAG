"""What the encoder learns about this machine, it should keep.

The backoff that recovers from a GPU running out of memory used to live in a
local variable, so every document began at the configured batch size, met the
same wall, and reloaded the model to get past it. It also doubled the batch
back up after a single success, so a machine that could sustain four
oscillated between four and eight, paying a model reload on every swing.
Measured during a corpus rebuild, that cost twenty-four recoveries in ninety
seconds while five documents completed.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.ingestion.embedder import BGEM3Embedder

DIMENSION = settings.embedding_dimension


class FakeEncoder:
    """Refuses any batch larger than `ceiling`, the way MPS does under pressure."""

    def __init__(self, ceiling: int) -> None:
        self.ceiling = ceiling
        self.attempted_sizes: list[int] = []
        self.loads = 0

    def encode(self, batch, **options):
        self.attempted_sizes.append(len(batch))
        if len(batch) > self.ceiling:
            raise RuntimeError("MPS backend out of memory")
        # The parser checks the dimension, so the fake must return vectors of
        # the size the configured model produces.
        return {
            "dense_vecs": [[0.0] * DIMENSION for _ in batch],
            "lexical_weights": [{"1": 0.5} for _ in batch],
        }


@pytest.fixture()
def embedder(monkeypatch):
    encoder = FakeEncoder(ceiling=4)
    instance = BGEM3Embedder(model_name="fake")
    monkeypatch.setattr(instance, "_load_model", lambda: (setattr(encoder, "loads", encoder.loads + 1), encoder)[1])
    monkeypatch.setattr(instance, "_release_model", lambda: None)
    monkeypatch.setattr(instance, "_clear_device_cache", lambda: None)
    instance._model_device = "mps"
    return instance, encoder


def test_the_reduced_batch_size_survives_into_the_next_document(embedder) -> None:
    instance, encoder = embedder
    instance.embed_texts([f"first {i}" for i in range(16)], batch_size=8)
    failures_first = sum(1 for size in encoder.attempted_sizes if size > encoder.ceiling)
    assert failures_first >= 1, "the fixture must provoke at least one backoff"

    encoder.attempted_sizes.clear()
    instance.embed_texts([f"second {i}" for i in range(16)], batch_size=8)
    assert all(size <= encoder.ceiling for size in encoder.attempted_sizes), (
        "the second document began at a size already known to fail"
    )


def test_it_does_not_oscillate_back_to_a_failing_size(embedder) -> None:
    instance, encoder = embedder
    # Long enough that a doubling rule would swing back up many times.
    instance.embed_texts([f"chunk {i}" for i in range(80)], batch_size=8)
    failures = sum(1 for size in encoder.attempted_sizes if size > encoder.ceiling)
    assert failures <= 2, f"batch size oscillated: {failures} failed attempts"


def test_it_tries_a_larger_batch_again_after_sustained_success(embedder) -> None:
    instance, encoder = embedder
    instance.embed_texts([f"chunk {i}" for i in range(200)], batch_size=8)
    assert max(encoder.attempted_sizes[-40:]) > 4 or instance._sustained_batch_size > 4, (
        "a machine that recovers should be offered a larger batch eventually"
    )


def test_every_text_is_embedded_despite_the_backoff(embedder) -> None:
    instance, _ = embedder
    result = instance.embed_texts([f"chunk {i}" for i in range(37)], batch_size=8)
    assert len(result) == 37
