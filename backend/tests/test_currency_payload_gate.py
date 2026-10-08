"""The gate that refuses a cutover when a warning did not reach the index.

Two manifest fields were dropped one hop before the retrieval payload, each
invisible from outside: `source_url`, so no citation could be opened, and
`currency_note`, so every doubtful document produced the same generic warning.
Run against the collection serving users at the time, this gate reported 733
of 733 indexed documents with no `currency_note` key at all, 332 recorded
warnings absent, and 724 recorded URLs absent.

The failure mode it exists for is a field that silently stops being written.
The symptom is a generic warning instead of a specific one, which a reader
notices and an engineer does not.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "check_currency_payload_gate.py"
SPEC = importlib.util.spec_from_file_location("check_currency_payload_gate", SCRIPT)
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


WARNED = (("Tenancy Act", "commencement"),)


def _document(**overrides):
    row = {
        "document_id": "doc-1",
        "title": "The Tenancy Act, 2017",
        "source_url": "https://indiacode.gov.in/x",
        "currency_note": "Section 1(3) requires a Gazette commencement notification, not located.",
        "current_status": "current/verify",
    }
    row.update(overrides)
    return {row["document_id"]: row}


def _payload(**overrides):
    payload = {
        "document_id": "doc-1",
        "title": "The Tenancy Act, 2017",
        "source_url": "https://indiacode.gov.in/x",
        "currency_note": "Section 1(3) requires a Gazette commencement notification, not located.",
        "is_current": False,
    }
    payload.update(overrides)
    return {payload["document_id"]: payload}


def test_a_complete_payload_passes() -> None:
    failures, summary = GATE.check(_document(), _payload(), WARNED, require_complete=True)
    assert failures == []
    assert summary["notes_missing_from_the_index"] == 0


def test_an_ingestion_predating_the_field_is_named_as_such() -> None:
    """The exact situation that produced this gate.

    Points written before the field existed have no key, and a resume would
    skip their documents rather than rewrite them, so the fix must be a
    rebuild. The message has to say that, or someone will resume.
    """
    payload = _payload()
    del payload["doc-1"]["currency_note"]
    failures, _ = GATE.check(_document(), payload, WARNED, require_complete=True)
    assert any("Rebuild rather than resume" in failure for failure in failures)


def test_a_recorded_warning_absent_from_the_index_fails() -> None:
    failures, _ = GATE.check(
        _document(), _payload(currency_note=""), WARNED, require_complete=True
    )
    assert any("absent" in failure and "currency warning" in failure for failure in failures)


def test_a_recorded_url_absent_from_the_index_fails() -> None:
    failures, _ = GATE.check(
        _document(), _payload(source_url=""), WARNED, require_complete=True
    )
    assert any("official URL that is absent" in failure for failure in failures)


def test_a_doubtful_instrument_indexed_as_current_law_fails() -> None:
    """The guardrail. Whatever else is true, this must never pass."""
    failures, _ = GATE.check(
        _document(), _payload(is_current=True), WARNED, require_complete=True
    )
    assert any("indexed as current law" in failure for failure in failures)


def test_a_doubtful_instrument_claiming_settled_status_fails() -> None:
    failures, _ = GATE.check(
        _document(current_status="current"), _payload(), WARNED, require_complete=True
    )
    assert any("asserts settled law" in failure for failure in failures)


def test_the_reason_changing_underneath_the_gate_fails() -> None:
    """A document flagged for one reason must not quietly acquire another.

    If the commencement evidence is later found, this gate should fail and be
    re-read, not keep passing on a warning that no longer describes anything.
    """
    failures, _ = GATE.check(
        _document(currency_note="Superseded by a later consolidation."),
        _payload(currency_note="Superseded by a later consolidation."),
        WARNED,
        require_complete=True,
    )
    assert any("no longer mentions" in failure for failure in failures)


def test_a_flagged_instrument_missing_from_the_manifest_fails() -> None:
    failures, _ = GATE.check({}, {}, WARNED, require_complete=False)
    assert any("not in the canonical manifest" in failure for failure in failures)


def test_an_unfinished_build_is_tolerated_until_the_cutover_check() -> None:
    """The gate is useful during a build and decisive before a cutover."""
    documents = {**_document(), "doc-2": {"document_id": "doc-2", "title": "Another Act"}}
    mid_build, _ = GATE.check(documents, _payload(), WARNED, require_complete=False)
    assert mid_build == []
    before_cutover, _ = GATE.check(documents, _payload(), WARNED, require_complete=True)
    assert any("the build is incomplete" in failure for failure in before_cutover)


def test_the_flagged_instruments_are_the_two_that_were_warned_about() -> None:
    fragments = " ".join(fragment for fragment, _ in GATE.DEFAULT_WARNED).lower()
    assert "tenancy" in fragments
    assert "motor vehicles rules" in fragments
    keywords = {keyword for _, keyword in GATE.DEFAULT_WARNED}
    assert keywords == {"commencement", "amendment"}
