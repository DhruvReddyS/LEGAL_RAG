from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

from qdrant_client import models

from app.core.config import settings
from app.core.qdrant import create_qdrant_client
from app.ingestion.chunker import LegalChunk
from app.ingestion.embedder import EmbeddingCache
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.ingestion.metadata import CanonicalDocument, iter_canonical_documents, load_manifest
from app.ingestion.pipeline import CheckpointStore
from app.ingestion.qdrant_writer import replace_document_chunks


def _is_substantive(text: str) -> bool:
    return bool(re.search(r"[^\W_]", text, flags=re.UNICODE))


def reconcile_embedding_cache(
    canonical_document_id: str, *, corpus_root: Path | None = None
) -> dict[str, Any]:
    """Atomically align a complete cache with the current ordered chunk file."""
    import gzip

    root = corpus_root or Path(settings.legal_kb_root)
    chunk_file = root / "processed/chunks" / f"{canonical_document_id}.jsonl"
    chunk_ids = [
        str(json.loads(line)["chunk_id"])
        for line in chunk_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cache = EmbeddingCache(root / "cache/embeddings")
    with gzip.open(cache._path(canonical_document_id), "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    old_ids = [str(value) for value in payload["chunk_ids"]]
    old_embeddings = EmbeddingCache._deserialize_embeddings(payload["embeddings"])
    by_id = dict(zip(old_ids, old_embeddings, strict=True))
    missing = [chunk_id for chunk_id in chunk_ids if chunk_id not in by_id]
    if missing:
        raise RuntimeError(f"Embedding cache is missing {len(missing)} current chunk(s)")
    cache.save(canonical_document_id, chunk_ids, [by_id[chunk_id] for chunk_id in chunk_ids])
    return {
        "canonical_document_id": canonical_document_id,
        "previous_embeddings": len(old_ids),
        "current_embeddings": len(chunk_ids),
        "removed_cache_entries": [chunk_id for chunk_id in old_ids if chunk_id not in set(chunk_ids)],
    }


def _chunk_from_payload(
    document: CanonicalDocument,
    payload: dict[str, Any],
) -> LegalChunk:
    return LegalChunk(
        chunk_id=str(payload["chunk_id"]),
        document_id=document.document_id,
        canonical_document_id=document.canonical_document_id,
        source_id=document.source_id,
        title=document.title,
        source_type=document.resolved_type().value,
        court=document.court,
        jurisdiction=document.jurisdiction,
        act_name=document.act_name,
        section=str(payload.get("section") or "") or None,
        subsection=str(payload.get("subsection") or "") or None,
        heading_path=[str(value) for value in payload.get("heading_path") or []],
        decision_date=document.decision_date,
        decision_year=document.decision_year,
        page_start=int(payload["page_start"]),
        page_end=int(payload["page_end"]),
        current_status=document.current_status,
        verified_official=document.verified_official,
        quality_status=document.quality_status,
        text=str(payload["text"]),
    )


async def restore_document_chunks(
    canonical_document_id: str,
    *,
    corpus_root: Path | None = None,
    apply: bool = False,
    update_qdrant: bool = False,
) -> dict[str, Any]:
    """Restore a damaged local chunk file from its durable Qdrant payloads.

    The complete embedding cache supplies the original chunk order.  Qdrant
    supplies the payload text and citation metadata.  Punctuation-only chunks
    are rejected using the same rule as the current chunker.
    """
    if update_qdrant and not apply:
        raise ValueError("--update-qdrant requires --apply")

    root = corpus_root or Path(settings.legal_kb_root)
    documents = {
        document.canonical_document_id: document
        for document in iter_canonical_documents(
            load_manifest(root / "metadata/canonical_documents.jsonl")
        )
    }
    try:
        document = documents[canonical_document_id]
    except KeyError as exc:
        raise ValueError(f"Unknown canonical document: {canonical_document_id}") from exc

    cache_path = root / "cache/embeddings"
    chunk_file = root / "processed/chunks" / f"{canonical_document_id}.jsonl"
    checkpoint = CheckpointStore(root / "logs/ingestion_checkpoint.json")
    client = create_qdrant_client()
    try:
        points, next_offset = await client.scroll(
            collection_name=GLOBAL_LEGAL_CORPUS,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="canonical_document_id",
                        match=models.MatchValue(value=canonical_document_id),
                    )
                ]
            ),
            limit=256,
            with_payload=True,
            with_vectors=False,
        )
        if next_offset is not None:
            raise RuntimeError("Document has more than 256 points; paginated restore is required")
        payloads = {
            str((point.payload or {}).get("chunk_id")): dict(point.payload or {})
            for point in points
        }
        if "None" in payloads:
            raise RuntimeError("Qdrant point is missing chunk_id")

        # Load the original ordered IDs from the complete cache, then retain the
        # matching embeddings for every substantive restored chunk.
        import gzip

        complete_path = cache_path / f"{canonical_document_id}.json.gz"
        with gzip.open(complete_path, "rt", encoding="utf-8") as handle:
            cache_payload = json.load(handle)
        ordered_ids = [str(value) for value in cache_payload["chunk_ids"]]
        all_embeddings = EmbeddingCache._deserialize_embeddings(cache_payload["embeddings"])
        if len(ordered_ids) != len(all_embeddings):
            raise RuntimeError("Embedding cache IDs and vectors have different lengths")
        missing = [chunk_id for chunk_id in ordered_ids if chunk_id not in payloads]
        if missing:
            raise RuntimeError(f"Qdrant is missing {len(missing)} cached chunk payload(s)")

        restored: list[LegalChunk] = []
        embeddings = []
        removed_chunk_ids: list[str] = []
        for chunk_id, embedding in zip(ordered_ids, all_embeddings, strict=True):
            chunk = _chunk_from_payload(document, payloads[chunk_id])
            if not _is_substantive(chunk.text):
                removed_chunk_ids.append(chunk_id)
                continue
            restored.append(chunk)
            embeddings.append(embedding)

        report = {
            "mode": "apply" if apply else "dry-run",
            "canonical_document_id": canonical_document_id,
            "qdrant_points_found": len(points),
            "cache_embeddings_found": len(all_embeddings),
            "restored_chunks": len(restored),
            "removed_non_substantive_chunks": removed_chunk_ids,
        }
        if not apply:
            return report

        temporary = chunk_file.with_suffix(chunk_file.suffix + ".tmp")
        temporary.write_text(
            "".join(chunk.model_dump_json() + "\n" for chunk in restored),
            encoding="utf-8",
        )
        os.replace(temporary, chunk_file)
        if update_qdrant:
            await replace_document_chunks(client, restored, embeddings)
        EmbeddingCache(cache_path).save(
            canonical_document_id,
            [chunk.chunk_id for chunk in restored],
            embeddings,
        )
        checkpoint.mark_completed(document, len(restored))
        return report
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore one local Gold chunk file from Qdrant and its embedding cache"
    )
    parser.add_argument("canonical_document_id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--update-qdrant", action="store_true")
    parser.add_argument("--reconcile-cache-only", action="store_true")
    args = parser.parse_args()
    if args.reconcile_cache_only:
        print(json.dumps(reconcile_embedding_cache(args.canonical_document_id), indent=2, sort_keys=True))
        return
    print(
        json.dumps(
            asyncio.run(
                restore_document_chunks(
                    args.canonical_document_id,
                    apply=args.apply,
                    update_qdrant=args.update_qdrant,
                )
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
