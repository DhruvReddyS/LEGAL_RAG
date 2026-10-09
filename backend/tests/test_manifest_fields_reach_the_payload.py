"""Three manifest fields in a row were declared nowhere and lost at the chunker.

The pattern, not the instances, is what this file is for.

`CanonicalDocument` sets `model_config` extra="allow". A field the acquisition
side records therefore parses, survives promotion, and is carried on the
document object -- while being invisible to every reader, because `LegalChunk`
has no such field and the chunker copies named fields only. The loss is silent
at every step:

    source_url      1,026 of 1,036 documents recorded one. 0 of 200 sampled
                    points in the serving collection carried it, so no
                    citation could be opened.
    currency_note   1,164 of 1,563 record why a document's currency is in
                    doubt. None reached a reader, so an Act whose commencement
                    notification was never located produced the same generic
                    warning as an unchecked circular.
    ocr_required    101 documents, 11,630 pages, 21% of the corpus. The
                    post-promotion audit says these "must not be treated as
                    searchable until OCR/extraction is verified". Nothing in
                    `backend/app` read the field at all.

Each was found by reading data rather than code, months apart. The last test
here is the one that matters: it fails when a field that a *majority* of the
manifest records is not declared on `CanonicalDocument`, which is the shape
all three had.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingestion.chunker import LegalChunk
from app.ingestion.metadata import CanonicalDocument
from app.ingestion.qdrant_writer import legal_chunk_payload


MANIFEST = Path(__file__).parents[2] / "data/legal_kb/metadata/canonical_documents.jsonl"

# Fields the acquisition side records that a reader depends on, and the
# payload key each must arrive under.
CARRIED_FIELDS = ("source_url", "currency_note", "ocr_required")

# Widely recorded and deliberately not carried to a chunk. Each needs a
# reason, so that "not carried" is a decision someone made rather than a field
# nobody noticed -- which is what the three losses above had in common.
ACQUISITION_ONLY: dict[str, str] = {
    "staged_at": "when promotion staged the record; bookkeeping for the acquisition log",
    "retrieved_on": "when the file was downloaded; bookkeeping for the acquisition log",
    # These two are not bookkeeping and are listed here under protest. A
    # citation excerpt reproduces up to 1,200 characters of the source, so the
    # licence a document arrived under is arguably a reader-facing fact and
    # certainly a product-facing one. It is tracked separately in
    # docs/evidence/corpus/copyright-register.md, which is the acquisition
    # side's record, and carrying it into the retrieval payload is a decision
    # for whoever owns the release rather than something to slip in through a
    # retrieval audit.
    "copyright_status": "tracked in the copyright register; carrying it is a release decision",
    "licence": "tracked in the copyright register; carrying it is a release decision",
}


def _rows() -> list[dict]:
    if not MANIFEST.exists():
        pytest.skip("no canonical manifest in this checkout")
    return [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()]


def _chunk_from(row: dict) -> LegalChunk:
    document = CanonicalDocument(
        **{key: value for key, value in row.items() if key in CanonicalDocument.model_fields}
    )
    return LegalChunk(
        chunk_id="c1",
        document_id=document.document_id,
        canonical_document_id=document.canonical_document_id,
        source_id=document.source_id,
        title=document.title,
        source_type=document.resolved_type().value,
        source_url=document.source_url,
        currency_note=document.currency_note,
        ocr_required=document.ocr_required,
        page_start=1,
        page_end=1,
        current_status=document.current_status,
        document_type="act",
        verified_official=document.verified_official,
        quality_status=document.quality_status,
        text="A provision.",
    )


@pytest.mark.parametrize("field", CARRIED_FIELDS)
def test_the_field_is_declared_rather_than_an_extra(field: str) -> None:
    """An `extra` parses and is then invisible. That is how all three were lost."""
    assert field in CanonicalDocument.model_fields, (
        f"{field} is arriving as a pydantic extra; it will be dropped at the chunker"
    )
    assert field in LegalChunk.model_fields, f"{field} has no field on the chunk to copy into"


@pytest.mark.parametrize("field", CARRIED_FIELDS)
def test_the_field_reaches_the_retrieval_payload(field: str) -> None:
    payload = legal_chunk_payload(_chunk_from(_rows()[0]))
    assert field in payload, f"{field} never reaches a reader"


def test_an_ocr_required_document_says_so_on_every_chunk() -> None:
    """The flag has to survive to the passage, not stop at the document.

    `classify_quality` cannot distinguish garbled extraction from a real
    provision -- OCR noise routinely clears six words and the
    operative-language test -- so the only way a reader learns which they are
    looking at is this field.
    """
    flagged = [row for row in _rows() if row.get("ocr_required")]
    if not flagged:
        pytest.skip("no OCR-required documents in this checkout's manifest")
    payload = legal_chunk_payload(_chunk_from(flagged[0]))
    assert payload["ocr_required"] is True


def test_a_document_with_extracted_text_is_not_flagged() -> None:
    extracted = [row for row in _rows() if row.get("ocr_required") is False]
    if not extracted:
        pytest.skip("no explicitly-extracted documents in this checkout's manifest")
    payload = legal_chunk_payload(_chunk_from(extracted[0]))
    assert payload["ocr_required"] is False


def test_the_key_is_always_present_even_when_unrecorded() -> None:
    """397 documents record neither True nor False.

    An absent key and a false one are different to a filter, so the payload
    carries a boolean either way rather than leaving the reader to guess
    whether absence means "extracted" or "nobody looked".
    """
    unrecorded = [row for row in _rows() if row.get("ocr_required") is None]
    if not unrecorded:
        pytest.skip("every document records the flag in this checkout")
    payload = legal_chunk_payload(_chunk_from(unrecorded[0]))
    assert payload["ocr_required"] is False
    assert "ocr_required" in payload


def test_no_widely_recorded_manifest_field_is_left_undeclared() -> None:
    """The guard against a fourth instance.

    A field recorded on most of the manifest is one the acquisition side
    considers part of the record. If `CanonicalDocument` does not declare it,
    it is being dropped before any reader, which is the exact shape of all
    three losses above.

    Deliberately a majority test rather than "any key": the manifest carries
    per-batch bookkeeping that genuinely belongs to acquisition alone, and a
    test that failed on those would be noise and would be switched off.
    """
    rows = _rows()
    threshold = len(rows) // 2
    counts: dict[str, int] = {}
    for row in rows:
        for key, value in row.items():
            if value not in (None, "", [], {}):
                counts[key] = counts.get(key, 0) + 1

    widely_recorded = {key for key, count in counts.items() if count > threshold}
    unaccounted = sorted(
        widely_recorded - set(CanonicalDocument.model_fields) - set(ACQUISITION_ONLY)
    )
    assert not unaccounted, (
        "recorded on most of the manifest, declared on no model and not listed as "
        "acquisition-only, so dropped before any reader without anyone deciding "
        f"that: {unaccounted}. Declare it on CanonicalDocument and carry it, or "
        "add it to ACQUISITION_ONLY with the reason."
    )


def test_every_acquisition_only_field_has_a_stated_reason() -> None:
    """The allowlist must not become a place to silence the test.

    An entry with an empty reason is the same silent drop in a different file.
    """
    for field, reason in ACQUISITION_ONLY.items():
        assert reason.strip(), f"{field} is excluded with no reason given"
        assert len(reason) > 20, f"{field}'s reason says too little to review"


def test_the_allowlist_does_not_hide_a_field_that_is_in_fact_carried() -> None:
    """A field cannot be both carried and declared acquisition-only."""
    assert not set(ACQUISITION_ONLY) & set(CARRIED_FIELDS)
    for field in ACQUISITION_ONLY:
        assert field not in CanonicalDocument.model_fields, (
            f"{field} is declared on the document model but listed as "
            "acquisition-only; the list is now misleading"
        )
