from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ingestion.classifier import LegalDocumentType, classify_document


class CanonicalDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    document_id: str
    canonical_document_id: str
    source_id: str
    title: str
    original_filename: str
    local_path: str
    source_type: str
    category: str
    authority: str | None = None
    jurisdiction: str | None = None
    court: str | None = None
    case_title: str | None = None
    case_number: str | None = None
    neutral_citation: str | None = None
    decision_date: str | None = None
    decision_year: int | None = None
    act_name: str | None = None
    section: str | None = None
    year: int | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    current_status: str
    supersedes: str | None = None
    superseded_by: str | None = None
    language: str = "English"
    source_url: str | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size: int = Field(gt=0)
    page_count: int = Field(gt=0)
    verified_official: bool
    duplicate_group: str | None = None
    quality_status: str
    notes: str | None = None
    document_type: LegalDocumentType | None = None

    def resolved_type(self) -> LegalDocumentType:
        return self.document_type or classify_document(self.model_dump())

    @property
    def is_current(self) -> bool:
        status = self.current_status.strip().lower()
        if "verify" in status or status in {"", "unknown", "uncertain"}:
            return False
        return status in {"current", "in force", "operative", "precedential"}


def load_manifest(path: Path) -> list[CanonicalDocument]:
    return [
        CanonicalDocument.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def iter_canonical_documents(documents: list[CanonicalDocument]) -> Iterator[CanonicalDocument]:
    """Yield exactly one physical source for each identical canonical content object."""
    seen: set[str] = set()
    for document in documents:
        if document.canonical_document_id in seen:
            continue
        seen.add(document.canonical_document_id)
        yield document


def manifest_summary(documents: list[CanonicalDocument]) -> dict[str, Any]:
    return {
        "physical_documents": len(documents),
        "canonical_documents": len({item.canonical_document_id for item in documents}),
        "verified_documents": sum(item.verified_official for item in documents),
    }
