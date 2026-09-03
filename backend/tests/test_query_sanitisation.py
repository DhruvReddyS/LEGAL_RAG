"""Inputs a user can actually send must never produce a 500.

Both cases here were found by probing a running server, and both returned
Internal Server Error after the request had already done work.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatQueryRequest


@pytest.mark.parametrize(
    ("label", "query"),
    [
        ("nul byte", "What is\x00 an FIR?"),
        ("bell", "What is an FIR\x07?"),
        ("vertical tab", "What is\x0b an FIR?"),
        ("delete", "What is\x7f an FIR?"),
    ],
)
def test_control_characters_never_reach_the_database(label: str, query: str) -> None:
    """PostgreSQL text cannot hold a NUL byte at all.

    One arriving from a PDF copy-paste failed the message insert with
    `invalid byte sequence for encoding "UTF8": 0x00` - a 500 returned only
    after retrieval and generation had already run.
    """
    cleaned = ChatQueryRequest(query=query).query

    assert "\x00" not in cleaned, label
    assert all(character.isprintable() or character == " " for character in cleaned), label
    assert "FIR" in cleaned, "sanitising must not destroy the question"


@pytest.mark.parametrize(
    "query",
    ["   ?   ", "?!?!?!", "\n\n\t\n", "...", "🙂🙂", "​​"],
)
def test_a_query_with_nothing_to_search_for_is_rejected_not_crashed(query: str) -> None:
    """A punctuation-only query produced no search terms.

    Retrieval then called min() on an empty set of term frequencies and raised,
    surfacing as a 500. Rejecting at the boundary gives the user a 422 and a
    reason instead.
    """
    with pytest.raises(ValidationError, match="letters or numbers|must not be blank"):
        ChatQueryRequest(query=query)


def test_ordinary_questions_are_untouched_apart_from_whitespace() -> None:
    assert (
        ChatQueryRequest(query="  Is FIR   registration\n mandatory?  ").query
        == "Is FIR registration mandatory?"
    )
    # Non-Latin scripts carry meaning and must survive.
    assert "प्राथमिकी" in ChatQueryRequest(query="प्राथमिकी दर्ज करना अनिवार्य है?").query


@pytest.mark.asyncio
async def test_lexical_retrieval_abstains_rather_than_raising_on_no_terms() -> None:
    """Validation should stop this reaching retrieval; a 500 is the wrong
    failure if it ever does."""
    from app.services.retrieval import HybridRetrievalService, RetrievalFilters, RetrievalTarget

    class _EmptyClient:
        async def scroll(self, **kwargs):
            return [], None

        async def count(self, **kwargs):
            class _Count:
                count = 0

            return _Count()

        async def close(self):
            return None

    service = HybridRetrievalService(client=_EmptyClient())  # type: ignore[arg-type]
    try:
        hits, timings = await service._search_lexical_target(
            target=RetrievalTarget(
                collection_name="global_legal_corpus", filters=RetrievalFilters()
            ),
            terms=set(),
            candidate_limit=8,
            result_limit=4,
        )
    finally:
        service._closed = True

    assert hits == []
    assert timings.candidate_count == 0
