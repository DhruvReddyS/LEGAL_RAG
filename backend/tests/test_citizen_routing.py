"""A citizen asking a plain question must get an answer, not an evidence brief.

Fast mode returns the closest corpus passages under a heading that says it does
not synthesise a legal opinion. For an advocate reading authority that is the
point; for a citizen asking what their rights are it is a non-answer.
"""
from __future__ import annotations

import pytest

from app.services.adaptive_routing import route_legal_query


CITIZEN_QUESTIONS = [
    "The police refused to register my FIR. What are my rights and what can I do?",
    "My landlord is keeping my deposit. What can I do?",
    "Can I get free legal aid?",
    "What happens if I am arrested?",
]


@pytest.mark.parametrize("question", CITIZEN_QUESTIONS)
def test_citizen_auto_queries_are_synthesised(question: str) -> None:
    decision = route_legal_query(query=question, requested_mode="auto", role="citizen")
    assert decision.selected_mode == "deep"
    assert decision.reason == "citizen_needs_a_synthesised_answer"


@pytest.mark.parametrize("question", CITIZEN_QUESTIONS)
def test_the_same_questions_still_take_fast_for_a_professional(question: str) -> None:
    # The change must not drag every role onto the slow path: a focused
    # authority lookup by an advocate or an officer still goes to Fast.
    for role in ("advocate", "police"):
        decision = route_legal_query(query=question, requested_mode="auto", role=role)
        assert decision.selected_mode == "fast", (role, question)


def test_an_explicit_mode_still_wins_for_a_citizen() -> None:
    # A citizen who deliberately asks for source inspection gets it.
    decision = route_legal_query(
        query="What are my rights?", requested_mode="fast", role="citizen"
    )
    assert decision.selected_mode == "fast"
    assert decision.reason == "user_selected"


def test_routing_without_a_role_is_unchanged() -> None:
    decision = route_legal_query(query="What are my rights?", requested_mode="auto")
    assert decision.selected_mode == "fast"
    assert decision.reason == "focused_authority_lookup"
