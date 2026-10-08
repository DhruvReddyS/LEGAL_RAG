"""The encoder stops rediscovering that this host cannot fit it.

On a CPU fallback the embedder released its model so the next document could
try the accelerator again. That is right when the shortage was transient -- one
long document caused it and the next is short. It is wrong when the shortage
is structural, and the v5 rebuild reached that state: the reasoning model, the
container stack holding Qdrant and Postgres, and the encoder do not fit in
24 GB at once. Measured in one run: 25 MPS out-of-memory recoveries and 12
falls back to CPU, one per document, each paying a full batch-size backoff and
two model loads to learn the same thing again.

Three consecutive fallbacks now latch the encoder to CPU for the rest of the
process. Three, so one awkward document does not surrender the accelerator for
a whole rebuild.
"""

from __future__ import annotations

from app.ingestion.embedder import (
    LATCH_AFTER_CONSECUTIVE_CPU_FALLBACKS,
    BGEM3Embedder,
)


def test_a_single_fallback_does_not_surrender_the_accelerator() -> None:
    """One long document must not cost a whole rebuild its accelerator."""
    embedder = BGEM3Embedder()
    embedder._consecutive_cpu_fallbacks = 1
    assert embedder._cpu_latched is False


def test_the_threshold_leaves_room_for_a_transient_shortage() -> None:
    assert LATCH_AFTER_CONSECUTIVE_CPU_FALLBACKS >= 2, "one document would latch the run"
    assert LATCH_AFTER_CONSECUTIVE_CPU_FALLBACKS <= 5, "too many wasted model loads before latching"
    assert BGEM3Embedder.LATCH_AFTER_CONSECUTIVE_CPU_FALLBACKS == LATCH_AFTER_CONSECUTIVE_CPU_FALLBACKS


def test_a_latched_embedder_loads_on_cpu_whatever_the_host_resolves_to(monkeypatch) -> None:
    """The latch has to be consulted where the device is chosen.

    Setting a flag that `_load_model` ignores would look like a fix and change
    nothing, which is the failure this test exists for.
    """
    embedder = BGEM3Embedder()
    embedder._cpu_latched = True
    monkeypatch.setattr("app.ingestion.embedder.resolve_embedding_device", lambda: "mps")

    loaded: dict[str, object] = {}

    class _FakeModel:
        def __init__(self, name, use_fp16, devices):
            loaded["devices"] = devices
            loaded["use_fp16"] = use_fp16

    import types

    fake_module = types.ModuleType("FlagEmbedding")
    fake_module.BGEM3FlagModel = _FakeModel  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "FlagEmbedding", fake_module)

    embedder._load_model()
    assert loaded["devices"] == "cpu"
    assert embedder._model_device == "cpu"


def test_an_unlatched_embedder_still_uses_the_resolved_device(monkeypatch) -> None:
    embedder = BGEM3Embedder()
    monkeypatch.setattr("app.ingestion.embedder.resolve_embedding_device", lambda: "mps")

    loaded: dict[str, object] = {}

    class _FakeModel:
        def __init__(self, name, use_fp16, devices):
            loaded["devices"] = devices

    import types

    fake_module = types.ModuleType("FlagEmbedding")
    fake_module.BGEM3FlagModel = _FakeModel  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "FlagEmbedding", fake_module)

    embedder._load_model()
    assert loaded["devices"] == "mps"


def test_embedding_an_empty_list_touches_nothing() -> None:
    """The latch must not change the trivial path."""
    embedder = BGEM3Embedder()
    assert embedder.embed_texts([]) == []
    assert embedder._model is None
