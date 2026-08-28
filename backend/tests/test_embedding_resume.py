from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from app.core.config import settings
from app.ingestion.embedder import BGEM3Embedder, EmbeddedText, EmbeddingCache


def _embedding(seed: int) -> EmbeddedText:
    return EmbeddedText(
        dense=[float(seed)] * settings.embedding_dimension,
        sparse={seed: float(seed) / 10},
    )


def test_complete_cache_format_remains_compatible(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path)
    chunk_ids = ["chunk-1", "chunk-2"]
    expected = [_embedding(1), _embedding(2)]

    cache.save("document", chunk_ids, expected)

    path = tmp_path / "document.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert set(payload) == {"model", "chunk_ids", "embeddings"}
    assert payload["chunk_ids"] == chunk_ids
    assert cache.load("document", chunk_ids) == expected


def test_load_prefix_uses_only_longest_contiguous_valid_parts(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path)
    chunk_ids = [f"chunk-{index}" for index in range(6)]
    cache.save_part("document", 0, chunk_ids[0:2], [_embedding(0), _embedding(1)])
    cache.save_part("document", 2, chunk_ids[2:4], [_embedding(2), _embedding(3)])
    cache.save_part("document", 5, chunk_ids[5:6], [_embedding(5)])
    cache.save_part(
        "document",
        4,
        ["stale-chunk"],
        [_embedding(99)],
    )

    prefix = cache.load_prefix("document", chunk_ids)

    assert prefix == [_embedding(0), _embedding(1), _embedding(2), _embedding(3)]


def test_part_from_another_model_is_not_reused(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path)
    chunk_ids = ["chunk-1"]
    cache.save_part(
        "document",
        0,
        chunk_ids,
        [_embedding(1)],
        model_name="old-model",
    )

    assert cache.load_prefix("document", chunk_ids, model_name="new-model") == []


def test_final_save_atomically_replaces_cache_and_cleans_parts(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path)
    chunk_ids = ["chunk-1", "chunk-2"]
    embeddings = [_embedding(1), _embedding(2)]
    cache.save_part("document", 0, chunk_ids[:1], embeddings[:1])

    cache.save("document", chunk_ids, embeddings)

    assert cache.load("document", chunk_ids) == embeddings
    assert not (tmp_path / ".parts" / "document").exists()
    assert not list(tmp_path.rglob("*.tmp"))


def test_incomplete_embeddings_cannot_be_published_as_complete_cache(tmp_path: Path) -> None:
    cache = EmbeddingCache(tmp_path)

    with pytest.raises(ValueError, match="counts must match"):
        cache.save("document", ["chunk-1", "chunk-2"], [_embedding(1)])

    assert not (tmp_path / "document.json.gz").exists()


class _FakeModel:
    def encode(self, texts: list[str], **_: object) -> dict[str, list[object]]:
        return {
            "dense_vecs": [
                [float(index)] * settings.embedding_dimension
                for index, _text in enumerate(texts)
            ],
            "lexical_weights": [{str(index): 1.0} for index, _text in enumerate(texts)],
        }


class _IndexFailModel:
    def __init__(self) -> None:
        self.calls = 0

    def encode(self, texts: list[str], **_: object) -> dict[str, list[object]]:
        self.calls += 1
        raise IndexError("transient MPS indexing failure")


class _RuntimeFailModel:
    def __init__(self) -> None:
        self.calls = 0

    def encode(self, texts: list[str], **_: object) -> dict[str, list[object]]:
        self.calls += 1
        raise RuntimeError("not an indexing failure")


def test_embedder_callback_reports_each_completed_batch_with_absolute_offset() -> None:
    embedder = BGEM3Embedder("test-model", use_fp16=False)
    embedder._model = _FakeModel()
    embedder._model_device = "cpu"
    completed: list[tuple[int, int]] = []

    embeddings = embedder.embed_texts(
        ["a", "b", "c", "d", "e"],
        batch_size=2,
        start_index=7,
        on_batch=lambda start, batch: completed.append((start, len(batch))),
    )

    assert len(embeddings) == 5
    assert completed == [(7, 2), (9, 2), (11, 1)]


def test_second_mps_index_error_reloads_model_and_checkpoints_batch_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedder = BGEM3Embedder("test-model", use_fp16=False)
    broken_model = _IndexFailModel()
    replacement_model = _FakeModel()
    embedder._model = broken_model
    embedder._model_device = "mps"
    load_calls = 0
    collections = 0
    cache_clears = 0
    completed: list[tuple[int, int]] = []

    def load_model() -> object:
        nonlocal load_calls
        load_calls += 1
        if embedder._model is None:
            embedder._model = replacement_model
            embedder._model_device = "mps"
        return embedder._model

    def collect() -> int:
        nonlocal collections
        collections += 1
        return 0

    def clear_cache() -> None:
        nonlocal cache_clears
        cache_clears += 1

    monkeypatch.setattr(embedder, "_load_model", load_model)
    monkeypatch.setattr(embedder, "_clear_device_cache", clear_cache)
    monkeypatch.setattr("app.ingestion.embedder.gc.collect", collect)

    embeddings = embedder.embed_texts(
        ["a"],
        on_batch=lambda start, batch: completed.append((start, len(batch))),
        start_index=4,
    )

    assert len(embeddings) == 1
    assert broken_model.calls == 2
    assert load_calls == 2
    assert collections == 1
    assert cache_clears == 2
    assert embedder._model is replacement_model
    assert completed == [(4, 1)]


def test_mps_index_error_recovery_is_bounded_and_does_not_checkpoint_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedder = BGEM3Embedder("test-model", use_fp16=False)
    broken_model = _IndexFailModel()
    replacement_model = _IndexFailModel()
    embedder._model = broken_model
    embedder._model_device = "mps"
    load_calls = 0
    completed: list[tuple[int, int]] = []

    def load_model() -> object:
        nonlocal load_calls
        load_calls += 1
        if embedder._model is None:
            embedder._model = replacement_model
            embedder._model_device = "mps"
        return embedder._model

    monkeypatch.setattr(embedder, "_load_model", load_model)
    monkeypatch.setattr(embedder, "_clear_device_cache", lambda: None)
    monkeypatch.setattr("app.ingestion.embedder.gc.collect", lambda: 0)

    with pytest.raises(IndexError, match="transient MPS"):
        embedder.embed_texts(
            ["a"],
            on_batch=lambda start, batch: completed.append((start, len(batch))),
        )

    assert broken_model.calls == 2
    assert replacement_model.calls == 1
    assert load_calls == 2
    assert completed == []


def test_non_index_error_is_not_retried_or_reloaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedder = BGEM3Embedder("test-model", use_fp16=False)
    broken_model = _RuntimeFailModel()
    embedder._model = broken_model
    embedder._model_device = "mps"
    load_calls = 0

    def load_model() -> object:
        nonlocal load_calls
        load_calls += 1
        return broken_model

    monkeypatch.setattr(embedder, "_load_model", load_model)
    monkeypatch.setattr(embedder, "_clear_device_cache", lambda: None)

    with pytest.raises(RuntimeError, match="not an indexing failure"):
        embedder.embed_texts(["a"])

    assert broken_model.calls == 1
    assert load_calls == 1
