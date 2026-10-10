"""A complete build must not be reported as incomplete.

De-duplication elects one member of each duplicate group and does not embed
the rest: the same Act arriving as two scans is one document to retrieval,
with one set of vectors. The payload gate counted manifest rows, so a
finished v5 -- 1,566 rows, 1,563 canonical documents, all 1,563 indexed --
failed with "3 documents missing".

That mattered more than a confusing message. De-duplication is permanent, so
the row count can never be reached: the check could never pass on any real
corpus, and a cutover gated on it would have been blocked forever or waved
through by hand, which is how a gate stops meaning anything.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "check_currency_payload_gate", ROOT / "scripts" / "check_currency_payload_gate.py"
)
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
sys.modules["check_currency_payload_gate"] = gate
SPEC.loader.exec_module(gate)


def _row(document_id: str, canonical: str, **extra):
    row = {
        "document_id": document_id,
        "canonical_document_id": canonical,
        "title": f"Act {document_id}",
        "source_url": "https://indiacode.gov.in/x",
        "currency_note": "",
        "current_status": "current/verify",
    }
    row.update(extra)
    return row


def _payload(document_id: str, canonical: str, **extra):
    payload = {
        "document_id": document_id,
        "canonical_document_id": canonical,
        "source_url": "https://indiacode.gov.in/x",
        "currency_note": "",
    }
    payload.update(extra)
    return payload


def test_a_deduplicated_duplicate_does_not_count_as_a_missing_document():
    """Two manifest rows, one canonical document, one set of vectors. The
    unembedded duplicate is the design working, not a gap."""
    documents = {
        "doc-a": _row("doc-a", "canon-1"),
        "doc-a-dup": _row("doc-a-dup", "canon-1"),   # same Act, second scan
        "doc-b": _row("doc-b", "canon-2"),
    }
    payloads = {
        "doc-a": _payload("doc-a", "canon-1"),
        "doc-b": _payload("doc-b", "canon-2"),
    }

    failures, summary = gate.check(documents, payloads, (), require_complete=True)

    assert failures == [], f"a complete build was reported incomplete: {failures}"
    assert summary["canonical_documents_expected"] == 2
    assert summary["canonical_documents_indexed"] == 2


def test_a_genuinely_unbuilt_document_still_fails_the_gate():
    """The fix must not make the check vacuous. A canonical document with no
    vectors at all is a real incomplete build and must still be caught."""
    documents = {
        "doc-a": _row("doc-a", "canon-1"),
        "doc-b": _row("doc-b", "canon-2"),
        "doc-c": _row("doc-c", "canon-3"),
    }
    payloads = {"doc-a": _payload("doc-a", "canon-1")}

    failures, summary = gate.check(documents, payloads, (), require_complete=True)

    assert failures, "an unbuilt corpus passed the completeness check"
    assert "2 of 3 canonical documents are not indexed" in failures[0]
    assert summary["canonical_documents_indexed"] == 1


def test_completeness_is_not_checked_during_a_build():
    """Without --require-complete the gate runs against a partial build, so a
    payload field can be caught early rather than after a day of embedding."""
    documents = {"doc-a": _row("doc-a", "canon-1"), "doc-b": _row("doc-b", "canon-2")}
    payloads = {"doc-a": _payload("doc-a", "canon-1")}

    failures, _ = gate.check(documents, payloads, (), require_complete=False)

    assert failures == []


def test_a_recorded_url_absent_from_the_index_still_fails():
    """The gate's original purpose. A citation a reader cannot open is the
    defect it was written for, and the completeness fix must not weaken it."""
    documents = {"doc-a": _row("doc-a", "canon-1", source_url="https://indiacode.gov.in/real")}
    payloads = {"doc-a": _payload("doc-a", "canon-1", source_url="")}

    failures, _ = gate.check(documents, payloads, (), require_complete=True)

    assert any("official URL that is absent" in f for f in failures), failures
