"""Reaching the provision in force by following what the corpus cites.

The problem this solves, measured: BNSS s.173 answers "how is an FIR
registered?" and contains none of those words -- it says "information
relating to the commission of a cognizable offence". The section does not
appear in the top 100 for that question, while its own text retrieves it at
rank 1, so the index is sound and the gap is between statutory drafting and
how people ask.

What does rank is judgments about FIR registration, and they cite CrPC
s.154 because they predate the Sanhitas. The official concordance says
CrPC s.154 is now BNSS s.173.
"""

from __future__ import annotations

import pytest

from app.services.citation_following import (
    MAX_FOLLOWED,
    MIN_CITATIONS,
    provisions_worth_following,
)


class _Hit:
    def __init__(self, *provisions: str) -> None:
        self.payload = {"cited_provisions": list(provisions)}


def _keys(hits: list) -> list[tuple[str, str]]:
    return [(p.code, p.section) for p in provisions_worth_following(hits)]


class TestItReachesTheProvisionRetrievalCannot:
    def test_the_fir_question(self) -> None:
        """Judgments cite CrPC s.154; the concordance forwards it to BNSS
        s.173, which is the section that answers the question."""
        hits = [_Hit("crpc:154"), _Hit("crpc:154"), _Hit("crpc:154", "crpc:155")]

        assert ("BNSS", "173") in _keys(hits)

    def test_anticipatory_bail(self) -> None:
        hits = [_Hit("crpc:438"), _Hit("crpc:438"), _Hit("crpc:438")]

        assert _keys(hits)[0] == ("BNSS", "482")

    def test_the_most_cited_provision_comes_first(self) -> None:
        """The passages agree on what they rest on, and the order says so."""
        hits = [
            _Hit("crpc:154", "crpc:41"),
            _Hit("crpc:154"),
            _Hit("crpc:154"),
            _Hit("crpc:41"),
        ]

        assert _keys(hits)[0] == ("BNSS", "173")


class TestItDoesNotSwampTheAnswer:
    def test_a_single_citation_is_an_aside_not_a_holding(self) -> None:
        """One mention in one passage is not what the sources rest on.

        Without a floor, every provision a judgment names in passing would
        be fetched and shown as though the question were about it.
        """
        assert _keys([_Hit("crpc:154")]) == []
        assert MIN_CITATIONS >= 2

    def test_the_list_is_bounded(self) -> None:
        """A judgment can cite dozens of provisions.

        Fetching each successor would fill the answer with material the
        question never asked about, which is the failure this is meant to
        prevent rather than cause.
        """
        many = [
            _Hit(*[f"crpc:{100 + n}" for n in range(20)]),
            _Hit(*[f"crpc:{100 + n}" for n in range(20)]),
        ]

        assert len(provisions_worth_following(many)) <= MAX_FOLLOWED

    def test_a_code_still_in_force_is_not_followed(self) -> None:
        """A citation to the BNSS needs no forwarding; it is already the law
        in force, and following it would fetch the passage twice."""
        assert _keys([_Hit("bnss:35"), _Hit("bnss:35"), _Hit("bnss:35")]) == []

    def test_a_provision_with_no_successor_is_not_invented(self) -> None:
        """IPC s.124A was repealed without replacement.

        The concordance records that, and following it must yield nothing
        rather than the nearest-numbered section.
        """
        assert _keys([_Hit("ipc:124a"), _Hit("ipc:124a"), _Hit("ipc:124a")]) == []


class TestItIsDeterministic:
    def test_the_same_hits_give_the_same_order(self) -> None:
        """Retrieval order feeds a measurement and a CI gate."""
        hits = [_Hit("crpc:154", "crpc:41"), _Hit("crpc:154", "crpc:41")]

        assert _keys(hits) == _keys(hits)

    def test_equal_weights_break_on_the_provision(self) -> None:
        """Two provisions cited equally must not swap between runs."""
        hits = [_Hit("crpc:41", "crpc:154"), _Hit("crpc:41", "crpc:154")]
        first = _keys(hits)

        assert first == sorted(first, key=lambda item: (item[0], item[1])) or len(first) == 1


class TestDegenerateInput:
    def test_no_hits(self) -> None:
        assert provisions_worth_following([]) == []

    def test_hits_with_no_citations(self) -> None:
        assert provisions_worth_following([_Hit(), _Hit()]) == []

    @pytest.mark.parametrize("junk", ["", "nonsense", "crpc:", ":154", "unknown:154"])
    def test_malformed_references_are_ignored(self, junk: str) -> None:
        assert provisions_worth_following([_Hit(junk), _Hit(junk)]) == []


class TestTheLaneUsesIt:
    """Wiring a retrieval step is exactly the change that type-checks,
    passes every unit test of the step itself, and never runs."""

    def test_the_retrieval_node_fetches_followed_provisions(self) -> None:
        import inspect

        from app.agents import retrieval_agent

        body = inspect.getsource(retrieval_agent)
        assert "fetch_followed_provisions" in body, (
            "the retrieval node no longer follows citations; the governing "
            "provision becomes unreachable for questions whose vocabulary "
            "differs from the statute's"
        )
        assert "hits = hits + followed" in body, (
            "followed provisions are computed and discarded"
        )

    def test_a_failed_lookup_does_not_cost_the_answer(self) -> None:
        """Corroboration is a bonus, not a dependency.

        If the extra fetch raises, what retrieval found on its merits must
        still reach the reader.
        """
        import inspect

        from app.agents import retrieval_agent

        body = inspect.getsource(retrieval_agent)
        start = body.index("fetch_followed_provisions")
        window = body[start - 400 : start + 400]
        assert "try:" in window and "followed = []" in window, (
            "the followed-provision fetch is not guarded; a Qdrant hiccup "
            "would turn a working answer into an error"
        )
