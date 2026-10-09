"""The status endpoint must answer from the checkpoint alone.

`/ingestion/progress` counts Qdrant points, so it cannot be polled and cannot
be called at all without a live index. `/ingestion/status` exists to be polled,
which only holds while it stays off Qdrant and off the chunk files.
"""

from __future__ import annotations

import json

import pytest

from app.ingestion.pipeline import checkpoint_path_for
from app.routers.ingestion import ingestion_status


def _write_corpus(root, documents: int, completed: int) -> None:
    manifest = root / "metadata" / "canonical_documents.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        "".join(
            json.dumps(
                {
                    "document_id": f"doc-{index}",
                    "canonical_document_id": f"canon-{index}",
                    "source_id": "test-source",
                    "title": f"Document {index}",
                    "original_filename": f"doc-{index}.pdf",
                    "local_path": f"pdfs/doc-{index}.pdf",
                    "source_type": "statute",
                    "category": "legislation",
                    "current_status": "in_force",
                    "sha256": f"{index:064d}",
                    "file_size": 1024,
                    "page_count": 1,
                    "verified_official": True,
                    "quality_status": "ok",
                }
            )
            + "\n"
            for index in range(documents)
        ),
        encoding="utf-8",
    )

    checkpoint = checkpoint_path_for(root)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(
        json.dumps({"completed": {f"doc-{index}": {"chunk_count": 1} for index in range(completed)}}),
        encoding="utf-8",
    )


@pytest.fixture
def kb_root(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "legal_kb_root", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("documents", "completed", "expected_status", "expected_percent"),
    [
        (0, 0, "not_started", 0.0),
        (4, 0, "not_started", 0.0),
        (4, 1, "in_progress", 25.0),
        (4, 4, "complete", 100.0),
    ],
)
async def test_status_reports_checkpoint_progress(
    kb_root, documents, completed, expected_status, expected_percent
):
    _write_corpus(kb_root, documents, completed)

    payload = await ingestion_status()

    assert payload["status"] == expected_status
    assert payload["total_documents"] == documents
    assert payload["completed_documents"] == completed
    assert payload["remaining_documents"] == documents - completed
    assert payload["percent"] == expected_percent


@pytest.mark.asyncio
async def test_status_does_not_touch_qdrant(kb_root, monkeypatch):
    """Polling is the point, so the route must not reach the index.

    Tested here rather than over the ASGI app so it does not need Postgres or
    the agent stack imported just to prove where the numbers come from.
    """
    _write_corpus(kb_root, 2, 1)

    def _no_qdrant():  # pragma: no cover - only runs on regression
        raise AssertionError("/ingestion/status must not touch Qdrant")

    monkeypatch.setattr("app.routers.ingestion.create_qdrant_client", _no_qdrant)

    payload = await ingestion_status()

    assert payload["status"] == "in_progress"
    assert payload["updated_at"] is not None
