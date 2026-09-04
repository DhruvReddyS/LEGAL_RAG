from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, Field

from app.ingestion.supersession import replacement_for
from app.ingestion.citations import extract_references, resolve_act
from app.ingestion.enrichment import (
    build_embed_text,
    classify_quality,
    structural_role,
)
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
    # Which structural unit this chunk came from, and where it sits inside it.
    # The chunker always knew this and hashed it into chunk_id without storing
    # it, so there was no way to ask for the rest of a section. Small-to-big
    # retrieval, judgment summarisation and drafting all need exactly that.
    unit_id: str = ""
    unit_ordinal: int = 0
    unit_count: int = 1
    # What kind of legal material this is: provision, proviso, ratio, order.
    structural_role: str = "prose"
    # Retrieval target. Carries the Act and heading the bare text omits; the
    # `text` field stays verbatim because citations quote it.
    embed_text: str = ""
    # "indexed" or "noise", with the reason recorded for review.
    quality: str = "indexed"
    quality_reason: str | None = None
    cited_provisions: list[str] = Field(default_factory=list)
    cited_cases: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    # Distinct from `superseded_by`, which drives `is_superseded` and means
    # "cannot ground a published claim". These two say the Act was repealed
    # and name what replaced it, while leaving it able to answer questions
    # about conduct before that date -- which the old codes still govern.
    replaced_by: str | None = None
    repealed_on: str | None = None
    verified_official: bool
    quality_status: str
    text: str

    @property
    def is_superseded(self) -> bool:
        """Whether a later instrument replaces this text.

        Eight guards across reasoning, verification, response generation and
        the analyzer read this. Until it was written it was always None, so
        every one of them was unreachable and read as implemented.
        """
        status = self.current_status.strip().lower()
        return bool(self.superseded_by) or "superseded" in status or "repealed" in status

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
    # Resolved once per document: an unqualified section reference inside an
    # Act means that Act.
    self_act = resolve_act(f"{document.act_name or ''} {document.title or ''}")
    # Also once per document: whether this Act has been repealed, and by what.
    replacement = replacement_for(document.act_name, document.title)
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
            unit_id = "gold-unit-" + hashlib.sha256(
                f"{document.canonical_document_id}|{unit_index}".encode()
            ).hexdigest()[:32]
            section = unit.section or document.section
            quality = classify_quality(piece, section=section)
            references = extract_references(piece, self_act=self_act)
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
                    unit_id=unit_id,
                    unit_ordinal=piece_index,
                    unit_count=len(pieces),
                    structural_role=structural_role(
                        piece, unit_kind=unit.kind, section=section
                    ),
                    embed_text=build_embed_text(
                        piece,
                        title=document.title,
                        act_name=document.act_name,
                        heading_path=unit.heading_path,
                        section=section,
                    ),
                    quality=quality.quality,
                    quality_reason=quality.reason,
                    cited_provisions=list(references.provisions),
                    cited_cases=list(references.cases),
                    superseded_by=document.superseded_by,
                    replaced_by=replacement.replaced_by if replacement else None,
                    repealed_on=replacement.repealed_on if replacement else None,
                    verified_official=document.verified_official,
                    quality_status=document.quality_status,
                    text=piece,
                )
            )
    return chunks
