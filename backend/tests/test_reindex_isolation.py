"""Building a second index must not disturb the first.

The cutover plan is: build a new collection alongside the live one, measure
both, and switch by changing a setting. That only holds if the two builds are
genuinely independent -- if they shared an ingestion ledger, a resumed build of
the new index would skip every document the live index had already finished,
and the new collection would come out empty while reporting success.
"""

from __future__ import annotations

from pathlib import Path

from app.ingestion.pipeline import DEFAULT_GLOBAL_COLLECTION, checkpoint_path_for


class TestCheckpointIsolation:
    def test_the_default_collection_keeps_its_original_ledger(self) -> None:
        """An existing ledger must still be found after this change.

        Renaming it would make the live corpus look entirely un-ingested.
        """
        path = checkpoint_path_for(Path("/kb"), DEFAULT_GLOBAL_COLLECTION)

        assert path == Path("/kb/logs/ingestion_checkpoint.json")

    def test_a_parallel_collection_gets_its_own_ledger(self) -> None:
        path = checkpoint_path_for(Path("/kb"), "global_legal_corpus_v2")

        assert path == Path("/kb/logs/ingestion_checkpoint.global_legal_corpus_v2.json")

    def test_two_collections_never_share_a_ledger(self) -> None:
        first = checkpoint_path_for(Path("/kb"), DEFAULT_GLOBAL_COLLECTION)
        second = checkpoint_path_for(Path("/kb"), "global_legal_corpus_v2")

        assert first != second

    def test_the_collection_defaults_to_the_configured_one(self) -> None:
        from app.core.config import settings

        assert checkpoint_path_for(Path("/kb")) == checkpoint_path_for(
            Path("/kb"), settings.qdrant_global_collection
        )


class TestCollectionIsConfigurable:
    def test_readers_and_writers_resolve_the_same_collection(self) -> None:
        """A cutover that moved readers but not writers would index into the
        old collection while querying the new one, and every answer would come
        from a corpus nothing was writing to."""
        from app.core.config import settings
        from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS

        assert GLOBAL_LEGAL_CORPUS == settings.qdrant_global_collection

    def test_the_collection_is_indexed_wherever_it_points(self) -> None:
        from app.ingestion.init_qdrant import COLLECTIONS, GLOBAL_LEGAL_CORPUS

        defined = {definition.name for definition in COLLECTIONS}
        assert GLOBAL_LEGAL_CORPUS in defined


class TestChunkFileIsolation:
    """Chunk files belong to a chunking contract, not to the corpus.

    Re-chunking in place would overwrite the files the live index was built
    from. The live index would then be unreproducible, and `validate` would
    compare it against a newer contract's chunks and report differences that
    are not defects.
    """

    def test_the_default_collection_keeps_the_original_directory(self) -> None:
        from app.ingestion.pipeline import DEFAULT_GLOBAL_COLLECTION, chunks_dir_for

        assert chunks_dir_for(Path("/kb"), DEFAULT_GLOBAL_COLLECTION) == Path(
            "/kb/processed/chunks"
        )

    def test_a_parallel_collection_writes_elsewhere(self) -> None:
        from app.ingestion.pipeline import chunks_dir_for

        assert chunks_dir_for(Path("/kb"), "global_legal_corpus_v2") == Path(
            "/kb/processed/chunks.global_legal_corpus_v2"
        )

    def test_a_rebuild_cannot_overwrite_the_live_corpus_chunks(self) -> None:
        from app.ingestion.pipeline import DEFAULT_GLOBAL_COLLECTION, chunks_dir_for

        live = chunks_dir_for(Path("/kb"), DEFAULT_GLOBAL_COLLECTION)
        rebuild = chunks_dir_for(Path("/kb"), "global_legal_corpus_v2")
        assert live != rebuild


class TestRechunkSkipsExtraction:
    def test_rechunk_is_a_distinct_option_from_force(self) -> None:
        """--force re-runs OCR over 381 PDFs; --rechunk reuses the cached text.

        Collapsing them would make every chunking experiment cost an OCR pass.
        """
        from app.ingestion.pipeline import PipelineOptions

        options = PipelineOptions(rechunk=True)
        assert options.rechunk is True
        assert options.force is False

    def test_rechunk_invalidates_the_embedding_cache(self) -> None:
        """Cached vectors describe the old chunk text.

        chunk_id is derived from the document and unit index, so an id can
        survive a re-chunk while the text behind it changes. Reusing the cache
        on that id would index the previous contract's vector under the new
        contract's text -- a corruption no test of the new index would catch,
        because the vector is well-formed and merely wrong.
        """
        import inspect

        from app.ingestion import pipeline

        source = inspect.getsource(pipeline.run_pipeline)
        assert "rebuilding = options.force or options.rechunk" in source
        assert "None if rebuilding else cache.load" in source


class TestEmbeddingCacheIsolation:
    """Cached vectors are contract-dependent, and the cache filename cannot
    say so: it names the document only. v1 embedded `chunk.text`, the current
    contract embeds `embed_text`, and a chunk id can survive a re-chunk
    unchanged -- so a shared cache hands back a vector of the old text under
    the new one. That corruption is invisible: the vector is well-formed and
    merely describes something else."""

    def test_the_default_collection_keeps_the_original_cache(self) -> None:
        from app.ingestion.pipeline import DEFAULT_GLOBAL_COLLECTION, embedding_cache_dir_for

        assert embedding_cache_dir_for(Path("/kb"), DEFAULT_GLOBAL_COLLECTION) == Path(
            "/kb/cache/embeddings"
        )

    def test_a_parallel_collection_caches_elsewhere(self) -> None:
        from app.ingestion.pipeline import embedding_cache_dir_for

        assert embedding_cache_dir_for(Path("/kb"), "global_legal_corpus_v2") == Path(
            "/kb/cache/embeddings.global_legal_corpus_v2"
        )

    def test_a_rebuild_cannot_overwrite_the_live_vectors(self) -> None:
        from app.ingestion.pipeline import DEFAULT_GLOBAL_COLLECTION, embedding_cache_dir_for

        live = embedding_cache_dir_for(Path("/kb"), DEFAULT_GLOBAL_COLLECTION)
        rebuild = embedding_cache_dir_for(Path("/kb"), "global_legal_corpus_v2")
        assert live != rebuild

    def test_every_per_collection_path_is_distinct(self) -> None:
        """The three kinds of shared state a parallel build would corrupt."""
        from app.ingestion.pipeline import (
            checkpoint_path_for,
            chunks_dir_for,
            embedding_cache_dir_for,
        )

        for collection in ("global_legal_corpus", "global_legal_corpus_v2"):
            paths = {
                checkpoint_path_for(Path("/kb"), collection),
                chunks_dir_for(Path("/kb"), collection),
                embedding_cache_dir_for(Path("/kb"), collection),
            }
            assert len(paths) == 3, collection
