import gzip
import json

from app.ingestion.restore_chunks import _is_substantive, reconcile_embedding_cache


def test_substantive_chunk_filter_rejects_punctuation_only_text() -> None:
    assert _is_substantive(":") is False
    assert _is_substantive(" -- \n … ") is False
    assert _is_substantive("Section 497") is True
    assert _is_substantive("धारा 497") is True


def test_reconcile_embedding_cache_removes_obsolete_entry(tmp_path) -> None:
    canonical_id = "gold-canonical-test"
    chunks = tmp_path / "processed/chunks"
    cache = tmp_path / "cache/embeddings"
    chunks.mkdir(parents=True)
    cache.mkdir(parents=True)
    (chunks / f"{canonical_id}.jsonl").write_text(
        json.dumps({"chunk_id": "keep"}) + "\n", encoding="utf-8"
    )
    embedding = {"dense": [0.0] * 1024, "sparse": {"1": 0.5}}
    with gzip.open(cache / f"{canonical_id}.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(
            {"model": "BAAI/bge-m3", "chunk_ids": ["keep", "obsolete"], "embeddings": [embedding, embedding]},
            handle,
        )

    report = reconcile_embedding_cache(canonical_id, corpus_root=tmp_path)

    assert report["current_embeddings"] == 1
    assert report["removed_cache_entries"] == ["obsolete"]
