"""A follow-up must not reach the lane that was given no history.

Fast is handed no conversation and resolves no references -- that is a
deliberate design choice, and a sound one. What was missing is the other
half: something had to stop a referring question from being routed there.
Nothing did, so "what about for a woman?" asked after a question about
arrest reached Fast, which searched for "woman" and answered about women
in general. Fluent, grounded, verified, and about the wrong subject.
"""

from __future__ import annotations

import pytest

from app.agents.query_understanding import is_self_contained, refers_backwards
from app.services.adaptive_routing import route_legal_query


def _mode(query: str, *, has_history: bool) -> str:
    return route_legal_query(
        query=query, requested_mode="auto", has_history=has_history
    ).selected_mode


class TestAReferringQuestionEscalates:
    @pytest.mark.parametrize(
        "query",
        [
            "what about for a woman?",
            "and if he refuses?",
            "can they do that?",
            "is that still true?",
            "explain that more simply",
            "what about section 35?",
            "and after 24 hours?",
            "does the same apply to a juvenile?",
            "what did you mean by that?",
        ],
    )
    def test_it_goes_to_the_lane_that_can_resolve_the_reference(self, query: str) -> None:
        assert _mode(query, has_history=True) == "deep"

    def test_the_signal_names_the_reason(self, query: str = "what about for a woman?") -> None:
        decision = route_legal_query(
            query=query, requested_mode="auto", has_history=True
        )

        assert "unresolved_backreference" in decision.signals


class TestWithoutHistoryNothingIsAFollowUp:
    @pytest.mark.parametrize(
        "query", ["what about for a woman?", "can they do that?", "is that still true?"]
    )
    def test_the_first_message_has_nothing_to_refer_to(self, query: str) -> None:
        """There is no prior turn, so the pronoun refers to nothing and Deep
        would resolve it against an empty history at thirty times the cost."""
        assert _mode(query, has_history=False) == "fast"


class TestAStandaloneQuestionStaysOnFast:
    @pytest.mark.parametrize(
        "query",
        [
            "What is the punishment for theft?",
            "How do I register an FIR?",
            "When can police arrest without a warrant?",
            "What is default bail?",
        ],
    )
    def test_being_in_a_conversation_does_not_by_itself_escalate(self, query: str) -> None:
        """The expensive mistake in the other direction.

        Escalating everything after the first message would send every
        follow-up question -- including complete ones -- through a lane that
        takes roughly thirty times as long, to resolve a reference that is
        not there.
        """
        assert _mode(query, has_history=True) == "fast"


class TestOneDefinitionOfABackwardReference:
    def test_the_router_and_the_rewriter_agree(self) -> None:
        """They must not drift.

        The Fast lane and its evaluation harness diverged four separate
        times in this project, each time behaving differently while looking
        identical. The router calls the same predicate the query rewriter
        uses rather than carrying its own copy of the pattern.
        """
        for query in ("what about for a woman?", "and if he refuses?", "is that still true?"):
            assert refers_backwards(query)
            assert _mode(query, has_history=True) == "deep"

        for query in ("What is the punishment for theft?", "How do I register an FIR?"):
            assert not refers_backwards(query)
            assert _mode(query, has_history=True) == "fast"

    def test_is_self_contained_still_treats_any_history_as_disqualifying(self) -> None:
        """Extracting the predicate must not have loosened the rewriter.

        The two callers want different things: the rewriter is conservative
        because a bad rewrite costs retrieval quality, while the router
        cannot escalate every turn. Sharing the pattern must not merge the
        policies.
        """
        assert is_self_contained("What is theft?", [])
        assert not is_self_contained("What is theft?", [{"role": "user", "content": "hi"}])
        assert not is_self_contained("what about that?", [])
