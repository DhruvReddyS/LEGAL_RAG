from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from qdrant_client import models

from app.core.config import settings
from app.core.qdrant import create_qdrant_client
from app.ingestion.chunker import LegalChunk
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.ingestion.metadata import iter_canonical_documents, load_manifest


async def normalize_gold_metadata(
    *,
    corpus_root: Path | None = None,
    apply: bool = False,
    update_qdrant: bool = False,
) -> dict[str, Any]:
    if update_qdrant and not apply:
        raise ValueError("--update-qdrant requires --apply")

    root = corpus_root or Path(settings.legal_kb_root)
    documents = list(
        iter_canonical_documents(load_manifest(root / "metadata/canonical_documents.jsonl"))
    )
    changed_files = 0
    changed_chunks = 0
    qdrant_documents = 0
    client = create_qdrant_client() if update_qdrant else None
    try:
        for document in documents:
            path = root / "processed/chunks" / f"{document.canonical_document_id}.jsonl"
            if not path.exists():
                continue
            chunks = [
                LegalChunk.model_validate_json(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            normalized_type = document.resolved_type().value
            updated = [
                chunk.model_copy(update={"source_type": normalized_type})
                for chunk in chunks
            ]
            file_changes = sum(
                before.source_type != after.source_type
                for before, after in zip(chunks, updated, strict=True)
            )
            if file_changes:
                changed_files += 1
                changed_chunks += file_changes
                if apply:
                    temporary = path.with_suffix(path.suffix + ".tmp")
                    temporary.write_text(
                        "".join(chunk.model_dump_json() + "\n" for chunk in updated),
                        encoding="utf-8",
                    )
                    os.replace(temporary, path)

            if client is not None:
                payload: dict[str, Any] = {
                    "source_type": normalized_type,
                    "is_current": document.is_current,
                }
                if document.decision_date:
                    payload["decision_date"] = f"{document.decision_date}T00:00:00Z"
                await client.set_payload(
                    collection_name=GLOBAL_LEGAL_CORPUS,
                    payload=payload,
                    points=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="canonical_document_id",
                                    match=models.MatchValue(
                                        value=document.canonical_document_id
                                    ),
                                )
                            ]
                        )
                    ),
                    wait=True,
                )
                qdrant_documents += 1
    finally:
        if client is not None:
            await client.close()

    return {
        "mode": "apply" if apply else "dry-run",
        "canonical_documents": len(documents),
        "changed_files": changed_files,
        "changed_chunks": changed_chunks,
        "qdrant_documents_updated": qdrant_documents,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize Gold source types and current-law payload flags"
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--update-qdrant", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                normalize_gold_metadata(
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
