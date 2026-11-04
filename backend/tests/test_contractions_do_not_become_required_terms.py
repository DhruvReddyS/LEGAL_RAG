"""Citizens write contractions, and the abstention gate must survive them."""

from __future__ import annotations

import pytest

from app.services.fast_research import _focus_tokens


@pytest.mark.parametrize(
    "query",
    [
        "The police didn't register my FIR",
        "The police didn’t register my FIR",
        "The police didnt register my FIR",
    ],
)
def test_a_negation_adds_no_search_term(query: str) -> None:
    tokens = _focus_tokens(query)
    assert {"police", "register", "fir"} <= tokens
    assert not tokens & {"didn", "didnt", "t"}


def test_a_possessive_keeps_its_noun() -> None:
    tokens = _focus_tokens("the landlord's deposit")
    assert "landlord" in tokens
    assert "s" not in tokens


def test_an_ordinary_word_ending_in_nt_is_untouched() -> None:
    assert "complaint" in _focus_tokens("my complaint against the agent")
    assert "agent" in _focus_tokens("my complaint against the agent")
