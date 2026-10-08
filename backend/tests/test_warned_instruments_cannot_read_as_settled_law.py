"""Two instruments are known to be doubtful, and the reader must be told why.

The agent acquiring the corpus flagged both and recorded the reason:

  - The Andhra Pradesh Residential and Non-Residential Premises Tenancy Act,
    2017: section 1(3) makes commencement depend on a Gazette notification
    that was never located, so it may not be in force at all.
  - The Central Motor Vehicles Rules, 1989: the official India Code copy is an
    old consolidation and MoRTH has issued later final amendments, including
    G.S.R. 48(E) of 20 January 2026.

Both carry `current_status = "current/verify"`, which resolves `is_current` to
False and puts them in the UNVERIFIED currency band -- and before this, the
band was all the reader got. Both lanes said "the current-law status of one or
more retrieved records is not verified", in the same words they used for a
circular nobody had got round to checking. The acquirer's reason was recorded
for 1,164 of 1,566 documents and reached nobody, because the chunk had no
field for it.

These tests pin that each warned instrument is named, with its reason, in both
lanes, and that `is_current` stays false for it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingestion.chunker import LegalChunk
from app.ingestion.metadata import CanonicalDocument
from app.ingestion.qdrant_writer import legal_chunk_payload
from app.services.currency import CurrencyStatus, resolve_currency
from app.services.fast_research import currency_notice


MANIFEST = Path(__file__).parents[2] / "data/legal_kb/metadata/canonical_documents.jsonl"

WARNED = (
    ("Andhra Pradesh Residential and Non-Residential Premises Tenancy", "commencement"),
    ("Central Motor Vehicles Rules, 1989", "amendment"),
)


def _documents():
    if not MANIFEST.exists():
        pytest.skip("no canonical manifest in this checkout")
    rows = [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows


def _document_named(fragment: str) -> dict:
    for row in _documents():
        if fragment.lower() in str(row.get("title") or "").lower():
            return row
    pytest.skip(f"{fragment} is not in this checkout's manifest")


def _payload_for(row: dict) -> dict:
    document = CanonicalDocument(
        **{key: value for key, value in row.items() if key in CanonicalDocument.model_fields}
    )
    chunk = LegalChunk(
        chunk_id="c1",
        document_id=document.document_id,
        canonical_document_id=document.canonical_document_id,
        source_id=document.source_id,
        title=document.title,
        source_type=document.resolved_type().value,
        source_url=document.source_url,
        currency_note=document.currency_note,
        act_name=document.act_name,
        page_start=1,
        page_end=1,
        current_status=document.current_status,
        document_type="act",
        verified_official=document.verified_official,
        quality_status=document.quality_status,
        text="Section 1. Short title, extent and commencement.",
    )
    return legal_chunk_payload(chunk)


@pytest.mark.parametrize(("fragment", "keyword"), WARNED)
def test_the_warning_survives_as_far_as_the_retrieval_payload(fragment: str, keyword: str) -> None:
    """The hop that lost it. Reading the manifest proves nothing on its own."""
    payload = _payload_for(_document_named(fragment))
    assert payload["currency_note"], "the acquirer's reason did not reach the payload"
    assert keyword in payload["currency_note"].lower()


@pytest.mark.parametrize(("fragment", "_keyword"), WARNED)
def test_neither_is_marked_current(fragment: str, _keyword: str) -> None:
    payload = _payload_for(_document_named(fragment))
    assert payload["is_current"] is False
    assert resolve_currency(payload).status is CurrencyStatus.UNVERIFIED


@pytest.mark.parametrize(("fragment", "keyword"), WARNED)
def test_the_fast_lane_names_the_instrument_and_the_reason(fragment: str, keyword: str) -> None:
    """Not "one or more retrieved records". A citizen cannot act on that."""
    payload = _payload_for(_document_named(fragment))
    notice = currency_notice([payload])
    assert notice is not None
    name = payload.get("act_name") or payload["title"]
    assert name in notice, "the notice does not say which instrument is doubtful"
    assert keyword in notice.lower(), "the notice does not say why"


def test_a_source_with_no_recorded_reason_is_still_listed_separately() -> None:
    """402 of 1,566 documents record no reason.

    Those must not silently vanish from the notice just because the better
    documented ones now have bullets of their own.
    """
    bare = {
        "act_name": "Some Unchecked Circular",
        "is_current": False,
        "current_status": "current/verify",
        "currency_note": "",
    }
    notice = currency_notice([bare])
    assert notice is not None
    assert "Some Unchecked Circular" in notice
    assert "no reason recorded" in notice


def test_a_fully_current_source_still_produces_no_notice() -> None:
    """The property that makes the notice worth reading.

    A warning that fires on every answer carries no information, which is the
    bug the previous version of this notice was fixed for.
    """
    current = {
        "act_name": "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "is_current": True,
        "is_superseded": False,
        "current_status": "current",
    }
    assert currency_notice([current]) is None
