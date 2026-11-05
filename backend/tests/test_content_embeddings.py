"""The same text under the same model is embedded once, ever."""

from __future__ import annotations

import pytest

from app.ingestion.content_embeddings import ContentEmbeddingStore, ReusingEmbedder
from app.ingestion.embedder import EmbeddedText


def _vector(text: str) -> EmbeddedText:
    return EmbeddedText(dense=[float(len(text)), 0.5, -0.25], sparse={len(text): 1.5, 7: 0.25})


class _Model:
    def __init__(self, name: str = "model-a", *, fail_after: int | None = None) -> None:
        self.model_name = name
        self.fail_after = fail_after
        self.seen: list[str] = []

    def embed_texts(self, texts, *, batch_size=8, on_batch=None, start_index=0):
        done = []
        for start in range(0, len(texts), batch_size):
            if self.fail_after is not None and len(self.seen) >= self.fail_after:
                raise RuntimeError("the process died")
            batch = texts[start : start + batch_size]
            self.seen.extend(batch)
            vectors = [_vector(text) for text in batch]
            done.extend(vectors)
            if on_batch:
                on_batch(start_index + start, vectors)
        return done


@pytest.fixture
def store(tmp_path) -> ContentEmbeddingStore:
    return ContentEmbeddingStore(tmp_path / "cache" / "content.sqlite")


def test_a_second_run_asks_the_model_nothing(store) -> None:
    first = ReusingEmbedder(_Model(), store).embed_texts(["one", "three"])
    model = _Model()
    embedder = ReusingEmbedder(model, store)
    assert embedder.embed_texts(["one", "three"]) == first
    assert model.seen == []
    assert embedder.reused == 2


def test_only_changed_text_is_embedded_and_order_is_kept(store) -> None:
    ReusingEmbedder(_Model(), store).embed_texts(["unchanged", "old"])
    model = _Model()
    result = ReusingEmbedder(model, store).embed_texts(["new text", "unchanged"])
    assert model.seen == ["new text"]
    assert result == [_vector("new text"), _vector("unchanged")]


def test_another_model_never_gets_these_vectors(store) -> None:
    ReusingEmbedder(_Model("model-a"), store).embed_texts(["same"])
    other = _Model("model-b")
    ReusingEmbedder(other, store).embed_texts(["same"])
    assert other.seen == ["same"]


def test_a_crash_keeps_every_finished_batch(store) -> None:
    texts = [f"text {n}" for n in range(6)]
    with pytest.raises(RuntimeError):
        ReusingEmbedder(_Model(fail_after=2), store).embed_texts(texts, batch_size=2)
    resumed = _Model()
    ReusingEmbedder(resumed, store).embed_texts(texts, batch_size=2)
    assert resumed.seen == texts[2:]


def test_a_repeat_within_one_call_is_embedded_once(store) -> None:
    model = _Model()
    result = ReusingEmbedder(model, store).embed_texts(["boilerplate", "x", "boilerplate"], batch_size=1)
    assert model.seen == ["boilerplate", "x"]
    assert result[0] == result[2]


def test_vectors_survive_storage_exactly(store) -> None:
    ReusingEmbedder(_Model(), store).embed_texts(["text"])
    assert ReusingEmbedder(_Model(), store).embed_texts(["text"]) == [_vector("text")]


def test_the_callers_batch_callback_still_gets_everything_in_place(store) -> None:
    calls = []
    ReusingEmbedder(_Model(), store).embed_texts(
        ["a", "b"], on_batch=lambda start, batch: calls.append((start, len(batch))), start_index=5
    )
    assert calls == [(5, 2)]


def test_other_attributes_reach_the_real_embedder(store) -> None:
    assert ReusingEmbedder(_Model("named"), store).model_name == "named"


def test_nothing_to_embed_is_nothing(store) -> None:
    assert ReusingEmbedder(_Model(), store).embed_texts([]) == []
