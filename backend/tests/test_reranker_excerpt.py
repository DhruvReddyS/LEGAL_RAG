"""Which part of a chunk the cross-encoder is shown.

Reranking cost grows worse than linearly with input, so a chunk longer than
the budget must be cut. Cutting it at the front spends the budget on wherever
the chunk happens to begin: 27.4% of corpus chunks exceed 2,500 characters and
lose 1,830 on average, always the tail. Measured against the golden set, the
cross-encoder *lowered* Recall@1 from 0.53 to 0.33 while costing 1,485 ms --
a reranker that makes ranking worse is worth understanding rather than
keeping.
"""

from __future__ import annotations

from app.services.retrieval import RERANKER_INPUT_CHARACTERS, reranker_excerpt


class TestShortChunksAreUntouched:
    def test_a_chunk_within_budget_is_returned_whole(self) -> None:
        text = "The officer shall reduce the information to writing."
        assert reranker_excerpt(text, "how is information recorded") == text

    def test_an_empty_chunk_is_safe(self) -> None:
        assert reranker_excerpt("", "anything") == ""


class TestTheWindowFollowsTheQuery:
    def test_the_relevant_tail_is_preferred_over_the_opening(self) -> None:
        """The failure this exists to fix.

        A chunk that opens on furniture and carries the provision late would
        be scored entirely on the furniture.
        """
        filler = "Preliminary matters and general provisions. " * 120
        provision = (
            "No woman shall be arrested after sunset and before sunrise except "
            "in exceptional circumstances and with prior permission."
        )
        text = filler + provision

        excerpt = reranker_excerpt(text, "when can a woman be arrested at night")

        assert "woman shall be arrested" in excerpt
        assert len(excerpt) <= RERANKER_INPUT_CHARACTERS

    def test_a_gazette_masthead_opening_does_not_win_the_budget(self) -> None:
        masthead = "jftLVªh lañ Mhñ ,yñ REGISTERED NO. DL 04/0007/2003 " * 60
        body = (
            "Any person aggrieved by an order of the Magistrate may prefer an "
            "appeal to the Court of Session within thirty days."
        )
        excerpt = reranker_excerpt(masthead + body, "appeal to Court of Session")

        assert "Court of Session" in excerpt

    def test_the_opening_still_wins_when_it_is_the_relevant_part(self) -> None:
        opening = (
            "Equality before law. The State shall not deny to any person "
            "equality before the law or the equal protection of the laws. "
        )
        tail = "Unrelated schedule entries and tabular matter. " * 120

        excerpt = reranker_excerpt(opening + tail, "equality before the law")

        assert excerpt.startswith("Equality before law")


class TestItNeverExceedsTheBudget:
    def test_a_very_long_chunk_is_bounded(self) -> None:
        text = "The Court held that the appeal shall be allowed. " * 2000

        excerpt = reranker_excerpt(text, "appeal allowed by the Court")

        assert len(excerpt) <= RERANKER_INPUT_CHARACTERS

    def test_a_query_with_no_usable_terms_falls_back_to_the_opening(self) -> None:
        text = "A" * 5000
        excerpt = reranker_excerpt(text, "what is the and or")

        assert excerpt == text[:RERANKER_INPUT_CHARACTERS]

    def test_a_query_matching_nothing_falls_back_to_the_opening(self) -> None:
        text = "Provisions concerning municipal drainage. " * 200
        excerpt = reranker_excerpt(text, "extradition treaty ratification")

        assert excerpt == text[:RERANKER_INPUT_CHARACTERS]
