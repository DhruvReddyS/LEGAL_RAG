"""A drafted FIR goes to a police station. It must say which provisions are dead.

The drafting lane retrieves with `current_only=False` on purpose, and the
comment at that call says it keeps "the mandatory professional currency
warning in the draft". There was no such warning. The disclaimer tells the
reader to verify "every fact, date, identity, jurisdiction and proposed legal
provision" -- an instruction to check, not a statement that a named provision
was replaced on 1 July 2024 and by what.

So a draft could list "The Indian Penal Code, 1860, section 378" under
POSSIBLE LEGAL AUTHORITIES FOR PROFESSIONAL REVIEW with nothing saying it was
replaced by the Bharatiya Nyaya Sanhita, and hand that to a complainant to
take to a police station. The IPC, CrPC and Evidence Act are 21% of this
corpus.

Every other lane already said it: Fast inline per citation, Deep in a Source
currency section, the advocate lane on the citation labels. This lane read the
payload itself and built a `DraftAuthority` with no currency fields at all --
the fifth currency divergence between lanes found in this audit, and the one
with the most consequential output.

No Qdrant, no embedder, no model.
"""

from __future__ import annotations

import pytest

from app.agents.drafting_agent import (
    PROFESSIONAL_REVIEW_DISCLAIMER,
    _draft_authority,
    authority_currency_note,
    render_fir,
)
from app.schemas.documents import DraftAuthority, FIRFacts


class _Hit:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.reranker_score = 0.5


REPEALED_IPC = {
    "chunk_id": "ipc-378",
    "title": "The Indian Penal Code, 1860",
    "act_name": "The Indian Penal Code, 1860",
    "section": "378",
    "page_start": 90,
    "page_end": 90,
    "text": "Whoever, intending to take dishonestly any movable property...",
}

IN_FORCE_BNS = {
    "chunk_id": "bns-303",
    "title": "The Bharatiya Nyaya Sanhita, 2023",
    "act_name": "The Bharatiya Nyaya Sanhita, 2023",
    "section": "303",
    "page_start": 55,
    "page_end": 55,
    "text": "Whoever commits theft shall be punished...",
    "is_current": True,
}


def _facts() -> FIRFacts:
    return FIRFacts(
        complainant_name="A. Complainant",
        complainant_contact="9999999999",
        incident_date="2026-10-01",
        incident_time="09:00",
        incident_location="Vijayawada",
        subject_or_property="a bicycle",
        narrative="The bicycle was taken from outside the house.",
    )


def test_a_repealed_authority_carries_its_status_on_the_draft_object() -> None:
    authority = _draft_authority(_Hit(REPEALED_IPC))
    assert authority.repeal_label == "no_longer_in_force"
    assert authority.current_status == "repealed"
    assert authority.replaced_by == "The Bharatiya Nyaya Sanhita, 2023"


def test_the_rendered_draft_says_the_provision_is_no_longer_in_force() -> None:
    """The assertion that matters: it has to be in the document, not the object.

    A field on a Pydantic model that no template prints is the same silence
    with more steps.
    """
    draft = render_fir(_facts(), [_draft_authority(_Hit(REPEALED_IPC))])
    assert "NO LONGER IN FORCE" in draft
    assert "The Bharatiya Nyaya Sanhita, 2023" in draft
    assert "section 378" in draft


def test_the_warning_sits_on_the_authority_line_itself() -> None:
    """Not in a footer.

    The reader of a draft takes the authority line to a police station. A
    warning elsewhere in the document is one the line does not carry.
    """
    draft = render_fir(_facts(), [_draft_authority(_Hit(REPEALED_IPC))])
    authority_line = next(
        line for line in draft.splitlines() if "section 378" in line
    )
    assert "NO LONGER IN FORCE" in authority_line


def test_an_in_force_provision_gets_no_warning() -> None:
    """A warning on every line carries no information."""
    draft = render_fir(_facts(), [_draft_authority(_Hit(IN_FORCE_BNS))])
    assert "NO LONGER IN FORCE" not in draft
    assert "not verified" not in draft


def test_an_unverified_provision_is_told_apart_from_a_repealed_one() -> None:
    """Three different facts, three different sentences.

    Marking an operative circular "repealed" because it cites a moved section
    would be false in the direction a police reader would catch immediately.
    """
    # A source the currency tables do not know and ingestion did not mark.
    # Both name fields have to change: `resolve_currency` matches on act_name
    # *or* title, so leaving the title as a known Act resolves it as that Act.
    unverified = {
        "chunk_id": "circ-1",
        "title": "Departmental circular on property receipts",
        "act_name": "Departmental circular on property receipts",
        "section": "4",
        "page_start": 2,
        "page_end": 2,
        "text": "Receipts shall be issued in the prescribed form.",
    }
    note = authority_currency_note(_draft_authority(_Hit(unverified)))
    assert "not verified" in note
    assert "NO LONGER IN FORCE" not in note


def test_a_renumbering_warning_is_its_own_sentence() -> None:
    item = DraftAuthority(
        chunk_id="j1",
        title="A 2025 judgment construing CrPC s.41",
        section="41",
        page_start=1,
        page_end=1,
        excerpt="...",
        reranker_score=0.5,
        current_status="current",
        repeal_label="concerns_repealed_provision",
    )
    note = authority_currency_note(item)
    assert "renumbered" in note
    assert "NO LONGER IN FORCE" not in note


def test_a_repealed_authority_with_no_recorded_successor_still_warns() -> None:
    """Saying nothing because the pointer is missing is the defect, not the fix."""
    item = DraftAuthority(
        chunk_id="m1",
        title="The Model Prison Manual",
        section="12",
        page_start=1,
        page_end=1,
        excerpt="...",
        reranker_score=0.5,
        current_status="repealed",
        repeal_label="no_longer_in_force",
        replaced_by=None,
    )
    note = authority_currency_note(item)
    assert "NO LONGER IN FORCE" in note
    assert "does not record what replaced it" in note


def test_a_draft_persisted_before_these_fields_still_loads() -> None:
    """The fields are optional for stored drafts, which are JSON on a row."""
    legacy = DraftAuthority(
        chunk_id="c1",
        title="An authority",
        section="1",
        page_start=1,
        page_end=1,
        excerpt="...",
        reranker_score=0.1,
    )
    assert legacy.repeal_label is None
    assert authority_currency_note(legacy) == ""


def test_the_disclaimer_is_still_there_and_is_not_the_currency_warning() -> None:
    """Both, and they say different things.

    The disclaimer asks the reader to verify the proposed provision. The
    currency note tells them which one is dead. The comment on the retrieval
    call claimed the first was the second.
    """
    draft = render_fir(_facts(), [_draft_authority(_Hit(REPEALED_IPC))])
    assert PROFESSIONAL_REVIEW_DISCLAIMER in draft
    assert "proposed legal provision" in PROFESSIONAL_REVIEW_DISCLAIMER
    assert "NO LONGER IN FORCE" not in PROFESSIONAL_REVIEW_DISCLAIMER
