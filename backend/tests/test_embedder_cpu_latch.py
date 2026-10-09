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
    REPROBE_ACCELERATOR_EVERY_DOCUMENTS,
    BGEM3Embedder,
)


def test_a_single_fallback_does_not_surrender_the_accelerator() -> None:
    """One long document must not cost a whole rebuild its accelerator."""
    embedder = BGEM3Embedder()
    embedder._consecutive_cpu_fallbacks = 1
    assert embedder._cpu_latched is False


def test_the_reprobe_interval_is_short_enough_to_notice_pressure_lifting() -> None:
    """The cost of asking was measured on this host with the machine idle: a
    2 s model load, and 2.93 GB peak driver memory for eight of the largest
    real chunks against a 17.76 GB working set. The encoder is not what
    exhausts this machine, so an OOM here is pressure from something else and
    it passes.

    At roughly a minute per document, probing every ten is under one percent
    of throughput. Fifty left the v5 build on the CPU for hours after the
    shortage had gone, because it had stopped asking often enough to notice.
    """
    assert REPROBE_ACCELERATOR_EVERY_DOCUMENTS >= 5, (
        "probing more often than every five documents spends more on model "
        "loads than a transient shortage costs"
    )
    assert REPROBE_ACCELERATOR_EVERY_DOCUMENTS <= 15, (
        "a longer interval is how a build stays on the CPU for hours after "
        "the memory pressure that caused the latch has gone"
    )
    assert BGEM3Embedder.REPROBE_ACCELERATOR_EVERY_DOCUMENTS == REPROBE_ACCELERATOR_EVERY_DOCUMENTS


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


def test_the_latch_reopens_after_enough_documents(monkeypatch) -> None:
    """A latch that never reopens is wrong for a job that runs for hours.

    Measured on the v5 build: it latched while the 14B reasoning model still
    held 11.7 GB of a 24 GB host, that model was unloaded twenty minutes
    later, and the rebuild then spent several hours on the CPU with zero
    out-of-memory events -- because it had stopped asking. The shortage it was
    protecting against had gone and nothing noticed.
    """
    embedder = BGEM3Embedder()
    embedder._cpu_latched = True
    embedder._documents_since_latch = BGEM3Embedder.REPROBE_ACCELERATOR_EVERY_DOCUMENTS - 1

    released: list[bool] = []
    monkeypatch.setattr(embedder, "_release_model", lambda: released.append(True))
    monkeypatch.setattr(
        embedder, "_encode_batch", lambda batch, options: {"dense_vecs": [], "lexical_weights": []}
    )
    monkeypatch.setattr(embedder, "_parse_output", lambda output, expected: [])

    embedder.embed_texts(["a provision"], batch_size=1)

    assert embedder._cpu_latched is False, "the latch did not reopen"
    assert released, "the CPU model must be released so the device is resolved again"
    assert embedder._documents_since_latch == 0


def test_the_latch_holds_until_the_reprobe_interval(monkeypatch) -> None:
    """Reopening on every document would reinstate the thrash it prevents."""
    embedder = BGEM3Embedder()
    embedder._cpu_latched = True
    embedder._documents_since_latch = 0
    monkeypatch.setattr(embedder, "_release_model", lambda: None)
    monkeypatch.setattr(
        embedder, "_encode_batch", lambda batch, options: {"dense_vecs": [], "lexical_weights": []}
    )
    monkeypatch.setattr(embedder, "_parse_output", lambda output, expected: [])

    embedder.embed_texts(["a provision"], batch_size=1)
    assert embedder._cpu_latched is True
    assert embedder._documents_since_latch == 1


def test_the_reprobe_interval_is_worth_what_it_costs() -> None:
    """One probe is a model load plus, on failure, a batch backoff.

    Too frequent and it is the per-document thrash the latch exists to stop;
    too rare and a recovered host stays on the slow path for hours. The
    accelerator path measured 10-20x faster on this host, so the probe pays
    for itself quickly.
    """
    assert BGEM3Embedder.REPROBE_ACCELERATOR_EVERY_DOCUMENTS >= 10
    assert BGEM3Embedder.REPROBE_ACCELERATOR_EVERY_DOCUMENTS <= 200
