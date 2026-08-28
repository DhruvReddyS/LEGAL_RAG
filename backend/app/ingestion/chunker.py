from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, Field

from app.ingestion.metadata import CanonicalDocument
from app.ingestion.structure import StructuralUnit


class LegalChunk(BaseModel):
    chunk_id: str
    document_id: str
    canonical_document_id: str
    source_id: str
    title: str
    source_type: str
    court: str | None = None
    jurisdiction: str | None = None
    act_name: str | None = None
    section: str | None = None
    subsection: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    decision_date: str | None = None
    decision_year: int | None = None
    page_start: int
    page_end: int
    current_status: str
    verified_official: bool
    quality_status: str
    text: str

    @property
    def is_current(self) -> bool:
        status = self.current_status.strip().lower()
        if "verify" in status or status in {"", "unknown", "uncertain"}:
            return False
        return status in {"current", "in force", "operative", "precedential"}


def _token_windows(text: str, *, maximum_tokens: int, overlap_tokens: int) -> list[str]:
    """Token-boundary fallback for a structural unit that is too large."""
    matches = list(re.finditer(r"\S+", text))
    if len(matches) <= maximum_tokens:
        return [text.strip()]
    windows: list[str] = []
    start = 0
    stride = maximum_tokens - overlap_tokens
    while start < len(matches):
        end = min(start + maximum_tokens, len(matches))
        char_start = matches[start].start()
        char_end = matches[end - 1].end()
        windows.append(text[char_start:char_end].strip())
        if end == len(matches):
            break
        start += stride
    return windows


def chunk_structural_units(
    document: CanonicalDocument,
    units: list[StructuralUnit],
    *,
    maximum_tokens: int = 700,
    overlap_tokens: int = 80,
) -> list[LegalChunk]:
    chunks: list[LegalChunk] = []
    for unit_index, unit in enumerate(units):
        if not unit.text.strip():
            continue
        pieces = _token_windows(
            unit.text,
            maximum_tokens=maximum_tokens,
            overlap_tokens=overlap_tokens,
        )
        for piece_index, piece in enumerate(pieces):
            if not re.search(r"[^\W_]", piece, re.UNICODE):
                continue
            stable_input = (
                f"{document.canonical_document_id}|{unit_index}|{piece_index}|"
                f"{unit.page_start}|{unit.page_end}|{piece}"
            )
            chunk_id = "gold-chunk-" + hashlib.sha256(stable_input.encode()).hexdigest()[:32]
            chunks.append(
                LegalChunk(
                    chunk_id=chunk_id,
                    document_id=document.document_id,
                    canonical_document_id=document.canonical_document_id,
                    source_id=document.source_id,
                    title=document.title,
                    source_type=document.resolved_type().value,
                    court=document.court,
                    jurisdiction=document.jurisdiction,
                    act_name=document.act_name,
                    section=unit.section or document.section,
                    subsection=unit.subsection,
                    heading_path=unit.heading_path,
                    decision_date=document.decision_date,
                    decision_year=document.decision_year,
                    page_start=unit.page_start,
                    page_end=unit.page_end,
                    current_status=document.current_status,
                    verified_official=document.verified_official,
                    quality_status=document.quality_status,
                    text=piece,
                )
            )
    return chunks
