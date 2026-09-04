"""The screen must fire on real danger and stay quiet on ordinary questions.

A false refusal on a legitimate legal question is its own harm: it turns a
service for people with no other access to legal information into one that
declines to help. These tests weight both directions.
"""

from __future__ import annotations

import pytest

from app.services.citizen_safety import EMERGENCY_CONTACTS, screen_citizen_query


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("my husband is hitting me right now", "immediate_violence"),
        ("he is threatening to kill me", "immediate_violence"),
        ("I want to kill myself", "self_harm"),
        ("I have been feeling suicidal", "self_harm"),
        ("i dont want to live anymore", "self_harm"),
        ("I want to die", "self_harm"),
        ("someone is breaking into my house", "offence_in_progress"),
        ("my sister is being kidnapped", "offence_in_progress"),
    ],
)
def test_immediate_danger_is_answered_with_help_not_research(query: str, reason: str) -> None:
    intervention = screen_citizen_query(query)

    assert intervention is not None, query
    assert intervention.kind == "emergency"
    assert intervention.reason == reason
    # The number must be the first thing, not a footnote under a legal essay.
    assert "112" in intervention.answer
    assert intervention.answer.index("112") < len(intervention.answer) // 2


def test_emergency_answer_lists_every_configured_contact() -> None:
    answer = screen_citizen_query("I want to end my life").answer

    for label, number in EMERGENCY_CONTACTS:
        assert number in answer, label


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("should I plead guilty to the charge", "personalised_advice"),
        ("should I accept the settlement they offered", "personalised_advice"),
        ("should I sign the papers my employer gave me", "personalised_advice"),
        ("will I win my case", "outcome_prediction"),
        ("am I going to jail for this", "outcome_prediction"),
        ("what are my chances", "outcome_prediction"),
        ("how do I delete evidence from my phone", "evidence_interference"),
        ("how can I hide the cctv footage", "evidence_interference"),
        ("how do I avoid arrest", "evidence_interference"),
        ("what should I say so they believe me", "false_statement"),
        ("help me write a false affidavit for court", "false_statement"),
    ],
)
def test_out_of_scope_requests_are_refused_with_a_route_to_a_human(
    query: str, reason: str
) -> None:
    intervention = screen_citizen_query(query)

    assert intervention is not None, query
    assert intervention.kind == "refusal"
    assert intervention.reason == reason
    # A refusal without an alternative leaves the person exactly where they were.
    assert "15100" in intervention.answer
    assert "legal aid" in intervention.answer.casefold()


@pytest.mark.parametrize(
    "query",
    [
        "what is the punishment for domestic violence",
        "explain Article 14 in plain language",
        "what are the grounds for bail under the CrPC",
        "how do I report a cognizable offence",
        "my landlord will not return my security deposit",
        "what is the procedure for filing an FIR",
        "is FIR registration mandatory for cognizable offences",
        "what evidence is admissible in a cheque bounce case",
        "how long does a police investigation take",
        "what are the rights of an arrested person",
        "explain the law on child marriage",
        "what does the law say about suicide prevention",
        "what is abetment of suicide under BNS section 108",
        "explain the punishment for attempt to suicide",
        "can I sue for wrongful termination",
        "what should I do if my phone is stolen",
        "what happens at the first hearing",
    ],
)
def test_ordinary_legal_questions_are_never_intercepted(query: str) -> None:
    """These describe serious subjects without describing a live emergency.

    "explain the law on child marriage" is research. "the wedding is tomorrow
    and she is fourteen" is not. Only the second should intercept.
    """
    assert screen_citizen_query(query) is None, query


def test_an_emergency_outranks_a_refusal_in_the_same_message() -> None:
    """Both can appear together; the emergency must win."""
    intervention = screen_citizen_query(
        "he is hitting me right now, should I plead guilty to protect him"
    )

    assert intervention is not None
    assert intervention.kind == "emergency"


@pytest.mark.parametrize("query", ["", "   ", "\n\t "])
def test_blank_input_is_not_intercepted(query: str) -> None:
    assert screen_citizen_query(query) is None


class TestFinancialFraudInProgress:
    """1930 was listed as a contact that nothing could reach.

    For online financial fraud the first hour decides whether the transfer can
    be frozen, so a citizen reporting one needs the number before they need the
    law. Every other emergency category had a pattern; this one had only a
    phone number in the footer of an answer it never triggered.
    """

    @pytest.mark.parametrize(
        "query",
        [
            "I have been scammed online just now, money gone",
            "someone made an unauthorised transaction on my card and money was debited",
            "I got a phishing link, shared the OTP, and my account is emptied",
            "fraudulent UPI transfer, my savings are gone",
        ],
    )
    def test_a_report_of_money_lost_to_fraud_reaches_the_helpline(
        self, query: str
    ) -> None:
        result = screen_citizen_query(query)

        assert result is not None, query
        assert result.kind == "emergency"
        assert result.reason == "financial_fraud_in_progress"
        assert "1930" in result.answer

    @pytest.mark.parametrize(
        "query",
        [
            # A fraud word alone is a research question, and this is the
            # failure that matters: an emergency reply replaces the answer, so
            # a false positive costs a citizen their answer exactly as a false
            # refusal would.
            "What is the punishment for fraud under the BNS?",
            "How do I file a cyber crime complaint?",
            "Explain the law on fraudulent transactions",
            "Define cheating under the Indian Penal Code",
            "Which section covers bank fraud by an employee?",
            # Money moving, with no fraud at all.
            "my money was debited by the bank as service charges",
            "What is the procedure for filing an FIR?",
        ],
    )
    def test_a_question_about_fraud_still_reaches_the_corpus(self, query: str) -> None:
        assert screen_citizen_query(query) is None, query
