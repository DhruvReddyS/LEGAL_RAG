"""is_superseded must reach the payload, or its guards do nothing.

Eight places across reasoning, verification, response generation and the
document analyzer read this field to refuse a replaced authority. It was
written nowhere - absent from LegalChunk, from the Qdrant payload builder and
from the collection index - so every one of those guards was unreachable while
reading, to anyone grepping, as implemented.
"""

from __future__ import annotations

import pytest

from app.ingestion.chunker import LegalChunk
from app.ingestion.init_qdrant import COLLECTIONS, GLOBAL_LEGAL_CORPUS
from app.ingestion.qdrant_writer import _payload
from app.services.retrieval import RetrievalFilters


def _chunk(**overrides) -> LegalChunk:
    base = dict(
        chunk_id="gold-chunk-1",
        document_id="gold-doc-1",
        canonical_document_id="gold-canonical-1",
        source_id="source-1",
        title="An Act",
        source_type="act",
        page_start=1,
        page_end=2,
        current_status="current/verify",
        verified_official=True,
        quality_status="verified",
        text="Some provision.",
    )
    return LegalChunk(**{**base, **overrides})


def test_payload_carries_the_field_the_guards_read() -> None:
    payload = _payload(_chunk())

    assert "is_superseded" in payload
    assert payload["is_superseded"] is False


@pytest.mark.parametrize(
    ("status", "superseded_by", "expected"),
    [
        ("current/verify", None, False),
        ("current", None, False),
        ("superseded", None, True),
        ("Repealed by later Act", None, True),
        # An explicit successor is decisive whatever the status string says.
        ("current/verify", "gold-canonical-2", True),
    ],
)
def test_supersession_is_derived_from_status_or_an_explicit_successor(
    status: str, superseded_by: str | None, expected: bool
) -> None:
    assert _chunk(current_status=status, superseded_by=superseded_by).is_superseded is expected


def test_an_unknown_status_is_not_treated_as_superseded() -> None:
    """Absent means unknown, not replaced.

    The whole corpus currently carries a "verify" status. Treating that as
    supersession would refuse every authority the system has.
    """
    assert _chunk(current_status="current/verify").is_superseded is False
    assert _chunk(current_status="").is_superseded is False


def test_the_field_is_indexed_so_a_filter_does_not_scan() -> None:
    corpus = next(item for item in COLLECTIONS if item.name == GLOBAL_LEGAL_CORPUS)

    assert "is_superseded" in corpus.payload_indexes


def test_superseded_authorities_can_be_excluded_at_the_query() -> None:
    """Excluding after ranking still lets a replaced provision take a slot.

    This previously asserted `must: is_superseded == False`, which is what the
    code did and was wrong. The field is tri-state in practice -- True, False,
    or absent on any index built before it existed -- and every one of the
    25,517 points in the live collection holds None. A positive match on False
    therefore excluded the entire corpus, so the filter would have returned
    nothing the first time anyone enabled it.

    The assertion is now the stronger one: exclude an explicit True, and never
    place a positive condition on this field.
    """
    query_filter = RetrievalFilters(exclude_superseded=True).to_qdrant()

    excluded = [
        condition
        for condition in (query_filter.must_not or [])
        if getattr(condition, "key", None) == "is_superseded"
    ]
    assert len(excluded) == 1
    assert excluded[0].match.value is True

    required = [
        condition
        for condition in (query_filter.must or [])
        if getattr(condition, "key", None) == "is_superseded"
    ]
    assert not required, "a positive match on this field excludes the whole corpus"

    # Off by default: the corpus cannot yet distinguish "not superseded" from
    # "unknown", so filtering by default would silently shrink retrieval.
    assert RetrievalFilters().exclude_superseded is False
