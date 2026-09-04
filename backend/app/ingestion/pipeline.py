from __future__ import annotations

import argparse
import asyncio
import errno
import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.qdrant import create_qdrant_client
from app.ingestion.chunker import LegalChunk, chunk_structural_units
from app.ingestion.dedup import verify_document_checksum
from app.ingestion.embedder import BGEM3Embedder, EmbeddedText, EmbeddingCache
from app.ingestion.extract import ExtractedDocument, extract_pdf
from app.ingestion.init_qdrant import initialize_qdrant
from app.ingestion.metadata import CanonicalDocument, iter_canonical_documents, load_manifest
from app.ingestion.qdrant_writer import replace_document_chunks
from app.ingestion.structure import parse_legal_structure


@dataclass
class PipelineOptions:
    resume: bool = False
    force: bool = False
    # Re-run structure parsing and chunking from cached extracted text, without
    # touching the PDFs. Every change to the chunk contract needs the corpus
    # rebuilt, and re-OCRing 381 documents to change how they are split is a
    # cost the extracted-text cache already paid.
    rechunk: bool = False
    document_id: str | None = None
    limit: int | None = None
    dry_run: bool = False
    embedding_batch_size: int = 8
    shard_index: int = 0
    shard_count: int = 1


@dataclass
class PipelineResult:
    selected_documents: int = 0
    completed_documents: int = 0
    skipped_documents: int = 0
    failed_documents: int = 0
    chunks_written: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


class CheckpointStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock_path = path.with_name(f"{path.name}.lock")
        self.claims_path = path.parent / f"{path.stem}_claims"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.claims_path.mkdir(parents=True, exist_ok=True)
        with self._lock():
            self.data = self._load_unlocked()

    def completed(self, document: CanonicalDocument) -> bool:
        with self._lock():
            self.data = self._load_unlocked()
        entry = self.data["completed"].get(document.canonical_document_id)
        return bool(entry and entry.get("sha256") == document.sha256)

    def mark_completed(self, document: CanonicalDocument, chunk_count: int) -> None:
        def update(data: dict[str, Any]) -> None:
            data["completed"][document.canonical_document_id] = {
                "document_id": document.document_id,
                "sha256": document.sha256,
                "chunk_count": chunk_count,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            data["failed"].pop(document.canonical_document_id, None)

        self._update(update)

    def mark_failed(self, document: CanonicalDocument, exc: Exception) -> None:
        def update(data: dict[str, Any]) -> None:
            completed = data["completed"].get(document.canonical_document_id)
            if completed and completed.get("sha256") == document.sha256:
                return
            data["failed"][document.canonical_document_id] = {
                "document_id": document.document_id,
                "error": f"{type(exc).__name__}: {exc}",
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }

        self._update(update)

    @contextmanager
    def claim(self, document: CanonicalDocument):
        """Try to hold this document's process claim until the context exits.

        Claim files are intentionally persistent: removing a locked file can let a
        later process lock a new inode while the old one is still held.  ``flock``
        releases the claim automatically if a worker exits or crashes.
        """
        claim_name = hashlib.sha256(
            document.canonical_document_id.encode("utf-8")
        ).hexdigest()
        claim_path = self.claims_path / f"{claim_name}.lock"
        with claim_path.open("a+", encoding="utf-8") as claim_file:
            try:
                fcntl.flock(
                    claim_file.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                    raise
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(claim_file.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _lock(self):
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"completed": {}, "failed": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data.setdefault("completed", {})
        data.setdefault("failed", {})
        return data

    def _update(self, mutation: Callable[[dict[str, Any]], None]) -> None:
        with self._lock():
            data = self._load_unlocked()
            mutation(data)
            self._save_unlocked(data)
            self.data = data

    def _save_unlocked(self, data: dict[str, Any]) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


DEFAULT_GLOBAL_COLLECTION = "global_legal_corpus"


def chunks_dir_for(root: Path, collection: str | None = None) -> Path:
    """Where the chunk files for one collection live.

    Chunks are an output of the chunking contract, not of the corpus, so two
    collections built from different contracts must not share a directory.
    Re-chunking in place would overwrite the files the live index was built
    from, leaving it unreproducible and making `validate` compare the live
    index against a newer contract's chunks.

    The default collection keeps the original path so existing files are found.
    """
    name = collection or settings.qdrant_global_collection
    if name == DEFAULT_GLOBAL_COLLECTION:
        return root / "processed/chunks"
    return root / f"processed/chunks.{name}"


def embedding_cache_dir_for(root: Path, collection: str | None = None) -> Path:
    """Where cached vectors for one collection live.

    The complete-cache file is named for the document alone, so a second
    collection writing here would overwrite the first collection's vectors and
    leave it unrestorable. The vectors are also contract-dependent in a way the
    filename cannot express: v1 embedded `chunk.text`, the current contract
    embeds `embed_text`, and a chunk id can survive a re-chunk unchanged. A
    shared cache would hand back a vector of the old text under the new one.

    The default collection keeps the original path so existing vectors are
    found.
    """
    name = collection or settings.qdrant_global_collection
    if name == DEFAULT_GLOBAL_COLLECTION:
        return root / "cache/embeddings"
    return root / f"cache/embeddings.{name}"


def checkpoint_path_for(root: Path, collection: str | None = None) -> Path:
    """Where the ingestion ledger for one collection lives.

    The ledger records which documents are already indexed, so it belongs to an
    index rather than to the corpus. Two collections built in parallel that
    shared a ledger would each skip the documents the other finished.

    The default collection keeps the original unsuffixed filename so an existing
    ledger is still found after this change.
    """
    name = collection or settings.qdrant_global_collection
    if name == DEFAULT_GLOBAL_COLLECTION:
        return root / "logs/ingestion_checkpoint.json"
    return root / f"logs/ingestion_checkpoint.{name}.json"


def select_shard(
    documents: list[CanonicalDocument], *, shard_index: int, shard_count: int
) -> list[CanonicalDocument]:
    """Select one stable, disjoint slice of the canonical manifest order."""
    return documents[shard_index::shard_count]


def _write_extracted(root: Path, extracted: ExtractedDocument, canonical_id: str) -> None:
    path = root / "processed/extracted_text" / f"{canonical_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(extracted.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _write_chunks(root: Path, chunks: list[LegalChunk], canonical_id: str) -> None:
    path = chunks_dir_for(root) / f"{canonical_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(chunk.model_dump_json() + "\n" for chunk in chunks),
        encoding="utf-8",
    )


async def run_pipeline(options: PipelineOptions, *, corpus_root: Path | None = None) -> PipelineResult:
    root = corpus_root or Path(settings.legal_kb_root)
    documents = list(
        iter_canonical_documents(load_manifest(root / "metadata/canonical_documents.jsonl"))
    )
    documents = select_shard(
        documents,
        shard_index=options.shard_index,
        shard_count=options.shard_count,
    )
    if options.document_id:
        documents = [
            item
            for item in documents
            if options.document_id in {item.document_id, item.canonical_document_id}
        ]
    result = PipelineResult()
    checkpoint = CheckpointStore(checkpoint_path_for(root))
    cache = EmbeddingCache(embedding_cache_dir_for(root))
    embedder = None if options.dry_run else BGEM3Embedder()
    qdrant = None
    if not options.dry_run:
        await initialize_qdrant()
        qdrant = create_qdrant_client()

    try:
        consecutive_failures = 0
        for document in documents:
            if options.resume and not options.force and checkpoint.completed(document):
                result.skipped_documents += 1
                continue
            if options.dry_run and options.resume and not options.force:
                extracted_path = root / "processed/extracted_text" / f"{document.canonical_document_id}.json"
                chunks_path = chunks_dir_for(root) / f"{document.canonical_document_id}.jsonl"
                if extracted_path.exists() and chunks_path.exists():
                    result.skipped_documents += 1
                    continue
            if options.limit is not None and result.selected_documents >= options.limit:
                break
            with checkpoint.claim(document) as claimed:
                if not claimed:
                    result.skipped_documents += 1
                    continue
                # Another worker may have completed the document after the fast
                # pre-check but before this worker acquired its claim.
                if options.resume and not options.force and checkpoint.completed(document):
                    result.skipped_documents += 1
                    continue
                result.selected_documents += 1
                try:
                    verify_document_checksum(document, root)
                    extracted_path = root / "processed/extracted_text" / f"{document.canonical_document_id}.json"
                    chunks_path = chunks_dir_for(root) / f"{document.canonical_document_id}.jsonl"
                    reuse_chunks = (
                        not options.force
                        and not options.rechunk
                        and extracted_path.exists()
                        and chunks_path.exists()
                    )
                    if reuse_chunks:
                        extracted = ExtractedDocument.model_validate_json(
                            extracted_path.read_text(encoding="utf-8")
                        )
                        chunks = [
                            LegalChunk.model_validate_json(line)
                            for line in chunks_path.read_text(encoding="utf-8").splitlines()
                            if line.strip()
                        ]
                        if extracted.document_id != document.document_id or any(
                            chunk.canonical_document_id != document.canonical_document_id
                            for chunk in chunks
                        ):
                            raise ValueError("Processed checkpoint metadata does not match manifest")
                        chunks = [
                            chunk.model_copy(
                                update={
                                    "title": document.title,
                                    "source_type": document.resolved_type().value,
                                    "court": document.court,
                                    "jurisdiction": document.jurisdiction,
                                    "act_name": document.act_name,
                                    "decision_date": document.decision_date,
                                    "decision_year": document.decision_year,
                                    "current_status": document.current_status,
                                    "verified_official": document.verified_official,
                                    "quality_status": document.quality_status,
                                }
                            )
                            for chunk in chunks
                        ]
                        _write_chunks(root, chunks, document.canonical_document_id)
                    else:
                        reused_extraction = options.rechunk and extracted_path.exists()
                        if reused_extraction:
                            extracted = ExtractedDocument.model_validate_json(
                                extracted_path.read_text(encoding="utf-8")
                            )
                            # The same integrity check the cached-chunk path
                            # makes. Text cached under one document's id but
                            # belonging to another would silently mis-attribute
                            # every citation drawn from it.
                            if extracted.document_id != document.document_id:
                                raise ValueError(
                                    "Cached extracted text does not match the manifest"
                                )
                        else:
                            extracted = await asyncio.to_thread(
                                extract_pdf,
                                root / document.local_path,
                                document_id=document.document_id,
                            )
                        units = parse_legal_structure(extracted, document.resolved_type())
                        chunks = chunk_structural_units(document, units)
                        # Furniture is classified at chunking and dropped here
                        # rather than filtered at query time, so it never
                        # occupies an embedding or a candidate slot.
                        rejected = [
                            chunk for chunk in chunks if chunk.quality != "indexed"
                        ]
                        chunks = [
                            chunk for chunk in chunks if chunk.quality == "indexed"
                        ]
                        if not reused_extraction:
                            _write_extracted(root, extracted, document.canonical_document_id)
                        _write_chunks(root, chunks, document.canonical_document_id)
                    if not chunks:
                        raise ValueError("No chunks were produced")

                    if options.dry_run:
                        result.completed_documents += 1
                        result.chunks_written += len(chunks)
                        print(
                            json.dumps(
                                {
                                    "event": "document_validated",
                                    "canonical_document_id": document.canonical_document_id,
                                    "chunks": len(chunks),
                                }
                            ),
                            flush=True,
                        )
                        continue

                    assert embedder is not None and qdrant is not None
                    chunk_ids = [chunk.chunk_id for chunk in chunks]
                    # A re-chunk invalidates the cache as thoroughly as --force
                    # does: the text behind each id has changed even where an id
                    # happens to survive, so a cached vector would describe the
                    # old chunk.
                    rebuilding = options.force or options.rechunk
                    embeddings = None if rebuilding else cache.load(
                        document.canonical_document_id,
                        chunk_ids,
                    )
                    if embeddings is None:
                        if rebuilding:
                            cache.cleanup_parts(document.canonical_document_id)
                            prefix: list[EmbeddedText] = []
                        else:
                            prefix = cache.load_prefix(
                                document.canonical_document_id,
                                chunk_ids,
                                model_name=embedder.model_name,
                            )
                        prefix_length = len(prefix)

                        def save_completed_batch(
                            start: int,
                            batch_embeddings: list[EmbeddedText],
                        ) -> None:
                            batch_chunk_ids = chunk_ids[start : start + len(batch_embeddings)]
                            cache.save_part(
                                document.canonical_document_id,
                                start,
                                batch_chunk_ids,
                                batch_embeddings,
                                model_name=embedder.model_name,
                            )

                        remaining = await asyncio.to_thread(
                            embedder.embed_texts,
                            # embed_text, not text. The retrieval target carries
                            # the Act and heading that the bare provision omits;
                            # `text` stays verbatim because citations quote it.
                            [
                                chunk.embed_text or chunk.text
                                for chunk in chunks[prefix_length:]
                            ],
                            batch_size=options.embedding_batch_size,
                            on_batch=save_completed_batch,
                            start_index=prefix_length,
                        )
                        embeddings = [*prefix, *remaining]
                        cache.save(document.canonical_document_id, chunk_ids, embeddings)
                    else:
                        # A crash can occur after the atomic final cache replace but
                        # before part cleanup. A valid final cache always wins.
                        cache.cleanup_parts(document.canonical_document_id)
                    written = await replace_document_chunks(qdrant, chunks, embeddings)
                    checkpoint.mark_completed(document, written)
                    consecutive_failures = 0
                    result.completed_documents += 1
                    result.chunks_written += written
                    print(
                        json.dumps(
                            {
                                "event": "document_ingested",
                                "canonical_document_id": document.canonical_document_id,
                                "chunks": written,
                            }
                        ),
                        flush=True,
                    )
                except Exception as exc:
                    consecutive_failures += 1
                    result.failed_documents += 1
                    result.errors.append(
                        {
                            "document_id": document.document_id,
                            "canonical_document_id": document.canonical_document_id,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    if not options.dry_run:
                        checkpoint.mark_failed(document, exc)
                    print(json.dumps(result.errors[-1]), flush=True)
                    if not options.dry_run and consecutive_failures >= 5:
                        print(
                            json.dumps(
                                {
                                    "event": "pipeline_stopped",
                                    "reason": "five_consecutive_failures",
                                }
                            ),
                            flush=True,
                        )
                        break
    finally:
        if qdrant is not None:
            await qdrant.close()
    return result


def parse_args() -> PipelineOptions:
    parser = argparse.ArgumentParser(description="Ingest the verified canonical Gold corpus")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--rechunk",
        action="store_true",
        help="Re-parse and re-chunk from cached extracted text, skipping OCR",
    )
    parser.add_argument("--document-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--embedding-batch-size", type=int, default=8)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be greater than zero")
    if args.shard_count < 1:
        parser.error("--shard-count must be greater than zero")
    if args.shard_index < 0 or args.shard_index >= args.shard_count:
        parser.error("--shard-index must be between zero and --shard-count - 1")
    return PipelineOptions(**vars(args))


def main() -> None:
    result = asyncio.run(run_pipeline(parse_args()))
    print(json.dumps(result.__dict__, indent=2, sort_keys=True))
    if result.failed_documents:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
