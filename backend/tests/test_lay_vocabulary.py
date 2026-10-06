"""A citizen's own words must reach the law written in someone else's words."""
from __future__ import annotations

import pytest

from app.services.lay_vocabulary import widen_for_retrieval


# Each of these returned no consumer, tenancy or cyber law at all before the
# bridge existed; the first one returned the Bharatiya Nyaya Sanhita.
BRIDGED = [
    ("I bought a defective phone online and the seller refuses a refund. What are my rights?",
     "consumer", "deficiency in service"),
    ("My landlord is not returning my security deposit. What can I do?",
     "tenancy", "security deposit"),
    ("Someone is harassing me online. What law applies?",
     "cyber_harassment", "cyber stalking"),
    ("My employer has not paid my wages for three months. What can I do?",
     "wages", "payment of wages"),
    ("My neighbour has encroached on my land. What is my remedy?",
     "land", "recovery of possession"),
    ("Can I get free legal aid?", "legal_aid", "legal services authority"),
    ("What compensation can I get after a road accident?", "accident", "motor accident claims tribunal"),
]


@pytest.mark.parametrize("question, domain, expected_term", BRIDGED)
def test_a_lay_question_is_widened_to_the_statutory_vocabulary(
    question: str, domain: str, expected_term: str
) -> None:
    widened, domains = widen_for_retrieval(question)
    assert domain in domains
    assert expected_term in widened
    # The person's own question must survive intact and lead the query.
    assert widened.startswith(question)


@pytest.mark.parametrize("question", [
    "What does Section 173 of the BNSS say?",
    "Explain Article 21 of the Constitution",
    "What is the punishment for theft?",
    "Summarise the Bharatiya Nyaya Sanhita, 2023",
])
def test_a_question_already_in_legal_language_is_left_alone(question: str) -> None:
    widened, domains = widen_for_retrieval(question)
    assert widened == question
    assert domains == ()


def test_at_most_two_domains_are_added() -> None:
    # A question touching many domains must not bury itself under vocabulary.
    busy = ("my landlord evicted me after a road accident while my employer withheld "
            "wages and the seller refused a refund and the police refused my FIR")
    widened, domains = widen_for_retrieval(busy)
    assert len(domains) <= 2
    assert widened.startswith(busy)
