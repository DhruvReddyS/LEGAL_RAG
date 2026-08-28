from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from qdrant_client import models

from app.ingestion.repair_metadata import normalize_gold_metadata


def _write_fixture(root: Path) -> Path:
    (root / "metadata").mkdir(parents=True)
    (root / "processed/chunks").mkdir(parents=True)
    manifest = {
        "document_id": "gold-doc-test",
        "canonical_document_id": "gold-canonical-test",
        "source_id": "url:test",
        "title": "Test Act",
        "original_filename": "test.pdf",
        "local_path": "raw/test.pdf",
        "source_type": "act",
        "category": "primary_law/other_relevant_laws",
        "current_status": "current",
        "sha256": "a" * 64,
        "file_size": 10,
        "page_count": 1,
        "verified_official": True,
        "quality_status": "verified",
    }
    (root / "metadata/canonical_documents.jsonl").write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )
    chunk = {
        "chunk_id": "gold-chunk-test",
        "document_id": "gold-doc-test",
        "canonical_document_id": "gold-canonical-test",
        "source_id": "url:test",
        "title": "Test Act",
        "source_type": "act",
        "jurisdiction": "India",
        "page_start": 1,
        "page_end": 1,
        "current_status": "current",
        "verified_official": True,
        "quality_status": "verified",
        "text": "Section 1 test provision.",
    }
    path = root / "processed/chunks/gold-canonical-test.jsonl"
    path.write_text(json.dumps(chunk) + "\n", encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_dry_run_reports_changes_without_touching_chunk_file(tmp_path: Path) -> None:
    chunk_path = _write_fixture(tmp_path)
    before = chunk_path.read_bytes()

    report = await normalize_gold_metadata(corpus_root=tmp_path)

    assert report == {
        "mode": "dry-run",
        "canonical_documents": 1,
        "changed_files": 1,
        "changed_chunks": 1,
        "qdrant_documents_updated": 0,
    }
    assert chunk_path.read_bytes() == before
    assert not chunk_path.with_suffix(".jsonl.tmp").exists()


class FakeQdrant:
    def __init__(self) -> None:
        self.payload_calls: list[dict[str, Any]] = []
        self.closed = False

    async def set_payload(self, **kwargs: Any) -> None:
        self.payload_calls.append(kwargs)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_apply_normalizes_file_and_matching_qdrant_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunk_path = _write_fixture(tmp_path)
    client = FakeQdrant()
    monkeypatch.setattr(
        "app.ingestion.repair_metadata.create_qdrant_client", lambda: client
    )

    report = await normalize_gold_metadata(
        corpus_root=tmp_path,
        apply=True,
        update_qdrant=True,
    )

    saved = json.loads(chunk_path.read_text(encoding="utf-8"))
    assert saved["source_type"] == "ACT"
    assert saved["chunk_id"] == "gold-chunk-test"
    assert saved["text"] == "Section 1 test provision."
    assert report["mode"] == "apply"
    assert report["changed_files"] == 1
    assert report["changed_chunks"] == 1
    assert report["qdrant_documents_updated"] == 1
    assert client.closed is True

    call = client.payload_calls[0]
    assert call["payload"] == {"source_type": "ACT", "is_current": True}
    assert call["wait"] is True
    selector = call["points"]
    assert isinstance(selector, models.FilterSelector)
    condition = selector.filter.must[0]
    assert isinstance(condition, models.FieldCondition)
    assert condition.key == "canonical_document_id"
    assert condition.match.value == "gold-canonical-test"


@pytest.mark.asyncio
async def test_qdrant_update_is_rejected_without_apply(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires --apply"):
        await normalize_gold_metadata(
            corpus_root=tmp_path,
            apply=False,
            update_qdrant=True,
        )
