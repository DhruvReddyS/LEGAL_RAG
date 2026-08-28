from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from qdrant_client import models

from app.core.config import settings
from app.core.qdrant import create_qdrant_client
from app.ingestion.init_qdrant import GLOBAL_LEGAL_CORPUS
from app.ingestion.metadata import iter_canonical_documents, load_manifest

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/progress")
async def ingestion_progress() -> dict:
    """Return corpus embedding progress from the ingestion checkpoint."""
    kb_root = Path(settings.legal_kb_root)
    manifest_path = kb_root / "metadata" / "canonical_documents.jsonl"
    checkpoint_path = kb_root / "logs" / "ingestion_checkpoint.json"

    total_documents = 0
    physical_documents = 0
    if manifest_path.exists():
        manifest = load_manifest(manifest_path)
        physical_documents = len(manifest)
        total_documents = sum(1 for _ in iter_canonical_documents(manifest))

    completed_documents = 0
    total_chunks = 0
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        completed = checkpoint.get("completed", {})
        completed_documents = len(completed)
        total_chunks = sum(entry.get("chunk_count", 0) for entry in completed.values())

    chunks_on_disk = sum(
        sum(1 for line in path.open(encoding="utf-8") if line.strip())
        for path in (kb_root / "processed/chunks").glob("*.jsonl")
    )

    percent = round(completed_documents / total_documents * 100, 1) if total_documents else 0.0
    status = "complete" if completed_documents >= total_documents and total_documents > 0 else "in_progress"
    qdrant = create_qdrant_client()
    try:
        gold_count = await qdrant.count(
            collection_name=GLOBAL_LEGAL_CORPUS,
            count_filter=models.Filter(
                must=[models.FieldCondition(key="corpus_tier", match=models.MatchValue(value="gold"))]
            ),
            exact=True,
        )
        extended_count = await qdrant.count(
            collection_name=GLOBAL_LEGAL_CORPUS,
            count_filter=models.Filter(
                must=[models.FieldCondition(key="corpus_tier", match=models.MatchValue(value="extended"))]
            ),
            exact=True,
        )
        qdrant_points = gold_count.count
        extended_points = extended_count.count
    finally:
        await qdrant.close()
    report_path = kb_root / "logs" / "ingestion_report.md"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    validation_status = (
        "pass"
        if qdrant_points == chunks_on_disk and "- Validation issues: 0" in report_text
        else "failed"
    )

    return {
        "total_documents": total_documents,
        "physical_documents": physical_documents,
        "canonical_documents": total_documents,
        "completed_documents": completed_documents,
        "remaining_documents": max(total_documents - completed_documents, 0),
        "total_chunks_indexed": total_chunks,
        "chunks_on_disk": chunks_on_disk,
        "percent": percent,
        "status": status,
        "validation_status": validation_status,
        "qdrant_points": qdrant_points,
        "extended_points": extended_points,
        "global_points": qdrant_points + extended_points,
    }
