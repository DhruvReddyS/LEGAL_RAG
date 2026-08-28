from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from qdrant_client import models

from app.core.config import settings
from app.ingestion.retrieval_smoke import validate_smoke_hits
from app.ingestion.validate import _expected_point_id, build_ingestion_report
from app.services.retrieval import RetrievalHit


class FakeValidationClient:
    def __init__(self, points: list[Any]) -> None:
        self.points = points

    async def get_collection(self, _: str) -> Any:
        return SimpleNamespace(points_count=len(self.points))

    async def scroll(self, **_: Any) -> tuple[list[Any], None]:
        return self.points, None


def _write_fixture(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    canonical_id = "gold-canonical-test"
    document_id = "gold-doc-test"
    chunk_id = "gold-chunk-test"
    for directory in (
        "metadata",
        "processed/chunks",
        "processed/extracted_text",
        "logs",
    ):
        (root / directory).mkdir(parents=True, exist_ok=True)
    manifest = {
        "document_id": document_id,
        "canonical_document_id": canonical_id,
        "source_id": "url:test",
        "title": "Test Act",
        "original_filename": "test.pdf",
        "local_path": "raw/test.pdf",
        "source_type": "act",
        "category": "primary_law/other_relevant_laws",
        "authority": "Test Authority",
        "jurisdiction": "India",
        "court": None,
        "case_title": None,
        "case_number": None,
        "neutral_citation": None,
        "decision_date": None,
        "decision_year": None,
        "act_name": "Test Act",
        "section": None,
        "year": 2024,
        "effective_from": None,
        "effective_to": None,
        "current_status": "current",
        "supersedes": None,
        "superseded_by": None,
        "language": "English",
        "source_url": "https://example.test/test.pdf",
        "sha256": "a" * 64,
        "file_size": 10,
        "page_count": 1,
        "verified_official": True,
        "duplicate_group": None,
        "quality_status": "verified",
        "notes": None,
    }
    (root / "metadata/canonical_documents.jsonl").write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )
    chunk = {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "canonical_document_id": canonical_id,
        "source_id": "url:test",
        "title": "Test Act",
        "source_type": "act",
        "court": None,
        "jurisdiction": "India",
        "act_name": "Test Act",
        "section": "1",
        "subsection": None,
        "heading_path": ["Section 1"],
        "decision_date": None,
        "decision_year": None,
        "page_start": 1,
        "page_end": 1,
        "current_status": "current",
        "verified_official": True,
        "quality_status": "verified",
        "text": "Section 1 test provision.",
    }
    (root / f"processed/chunks/{canonical_id}.jsonl").write_text(
        json.dumps(chunk) + "\n", encoding="utf-8"
    )
    extracted = {
        "document_id": document_id,
        "source_path": "raw/test.pdf",
        "pages": [
            {
                "page_number": 1,
                "text": chunk["text"],
                "original_page_text": chunk["text"],
                "extraction_method": "pymupdf",
                "ocr_used": False,
                "warnings": [],
            }
        ],
        "warnings": [],
    }
    (root / f"processed/extracted_text/{canonical_id}.json").write_text(
        json.dumps(extracted), encoding="utf-8"
    )
    checkpoint = {
        "completed": {
            canonical_id: {
                "document_id": document_id,
                "sha256": manifest["sha256"],
                "chunk_count": 1,
            }
        },
        "failed": {},
    }
    (root / "logs/ingestion_checkpoint.json").write_text(
        json.dumps(checkpoint), encoding="utf-8"
    )
    payload = {
        "chunk_id": chunk_id,
        "text": chunk["text"],
        "source_type": "act",
        "title": "Test Act",
        "act_name": "Test Act",
        "section": "1",
        "jurisdiction": "India",
        "court": "",
        "decision_year": 0,
        "is_current": True,
        "source_id": "url:test",
        "document_id": document_id,
        "canonical_document_id": canonical_id,
        "page_start": 1,
        "page_end": 1,
        "heading_path": ["Section 1"],
        "verified_official": True,
        "quality_status": "verified",
        "corpus_tier": "gold",
    }
    return chunk, payload


def _point(payload: dict[str, Any]) -> Any:
    return SimpleNamespace(
        id=_expected_point_id(payload["chunk_id"]),
        payload=payload,
        vector={
            settings.qdrant_dense_vector_name: [0.0] * settings.embedding_dimension,
            settings.qdrant_sparse_vector_name: models.SparseVector(
                indices=[1, 2], values=[0.5, 0.25]
            ),
        },
    )


@pytest.mark.asyncio
async def test_complete_ingestion_requires_exact_per_canonical_points(tmp_path: Path) -> None:
    _, payload = _write_fixture(tmp_path)
    report = await build_ingestion_report(
        corpus_root=tmp_path,
        require_complete=True,
        client=FakeValidationClient([_point(payload)]),
    )
    assert report["validation_issue_count"] == 0
    assert report["qdrant_gold_points"] == 1

    mismatched = dict(payload, chunk_id="gold-chunk-orphan")
    with pytest.raises(RuntimeError, match="validation failed"):
        await build_ingestion_report(
            corpus_root=tmp_path,
            require_complete=True,
            client=FakeValidationClient([_point(mismatched)]),
        )


@pytest.mark.asyncio
async def test_ingestion_validation_detects_payload_vector_and_orphan_issues(
    tmp_path: Path,
) -> None:
    _, payload = _write_fixture(tmp_path)
    invalid_payload = dict(payload)
    invalid_payload.pop("title")
    invalid_point = _point(invalid_payload)
    invalid_point.vector[settings.qdrant_dense_vector_name] = [0.0, 0.1]
    orphan_payload = dict(payload, canonical_document_id="gold-canonical-orphan")

    report = await build_ingestion_report(
        corpus_root=tmp_path,
        client=FakeValidationClient([invalid_point, _point(orphan_payload)]),
    )

    issues = "\n".join(report["validation_issues"])
    assert "missing payload fields: title" in issues
    assert "dense dimension is 2" in issues
    assert "orphan Gold point" in issues
    assert report["point_payload_vector_issues"] >= 2


def _retrieval_hit(**payload_updates: Any) -> RetrievalHit:
    payload = {
        "title": "FIR Registration Guidelines",
        "source_type": "official_guidance",
        "court": "",
        "act_name": "Code of Criminal Procedure",
        "section": "154",
        "page_start": 1,
        "page_end": 2,
        "corpus_tier": "gold",
        "verified_official": True,
        "text": "Registration of a first information report is mandatory.",
    }
    payload.update(payload_updates)
    return RetrievalHit(
        point_id="point",
        payload=payload,
        dense_score=0.7,
        sparse_score=3.0,
        fused_score=0.8,
        reranker_score=0.9,
    )


def test_smoke_validation_rejects_empty_wrong_tier_and_missing_concepts() -> None:
    assert validate_smoke_hits("mandatory FIR registration", [_retrieval_hit()]) == []
    assert validate_smoke_hits("mandatory FIR registration", []) == ["no results returned"]

    issues = validate_smoke_hits(
        "mandatory FIR registration",
        [
            _retrieval_hit(
                corpus_tier="extended",
                verified_official=False,
                title="Unrelated material",
                text="unrelated",
            )
        ],
    )
    assert "result 1 is not Gold corpus" in issues
    assert "result 1 is not verified official" in issues
    assert any(issue.startswith("expected concept absent") for issue in issues)


def test_smoke_validation_accepts_single_modality_and_page_cited_guidance() -> None:
    hit = _retrieval_hit(court="", act_name="", source_type="official_guidance")
    hit.dense_score = None

    assert validate_smoke_hits("mandatory FIR registration", [hit]) == []
