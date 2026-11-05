"""Foreign law is refused; Indian law with a foreign connection is not."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.fast_research import publishable_hits
from app.services.question_scope import asks_about_foreign_law


@pytest.mark.parametrize(
    "question",
    [
        "What are the visa requirements for studying in Canada?",
        "How do I apply for a United States green card?",
        "How do I get a divorce in England?",
        "What notice period applies to my job in Dubai?",
        "How do I renew my driving licence in Germany?",
        "What is the minimum wage in California?",
        "Can my landlord in Toronto raise the rent?",
        "How do I claim asylum in Australia?",
        "What does British law say about squatters?",
        "What are the laws of Singapore on chewing gum?",
    ],
)
def test_the_law_of_another_country_is_out_of_scope(question: str) -> None:
    assert asks_about_foreign_law(question)


@pytest.mark.parametrize(
    "question",
    [
        "My NRI husband in Canada has abandoned me. Can I file a case in India?",
        "My husband in Canada has stopped sending money. What can I do?",
        "My son who lives in Dubai was cheated by a recruiter. What can we do?",
        "Can a person be extradited from India to the United States?",
        "Can I be extradited to the United States?",
        "How is a foreign divorce decree treated by Indian courts?",
        "A foreign national overstayed their visa in India. What is the offence?",
        "Is a marriage in England valid under the Special Marriage Act?",
        "Can the High Court hear a case about a contract signed in Singapore?",
        "What should I do if the police refuse to register my FIR?",
        "Can the police search us in public?",
        "What rights are available to those of us in custody?",
        "My employer wants to send me abroad. Can they keep my certificates?",
        "My brother came from Dubai and customs seized his gold.",
    ],
)
def test_indian_law_with_a_foreign_connection_stays_in_scope(question: str) -> None:
    assert not asks_about_foreign_law(question)


def test_no_passage_can_be_published_for_a_foreign_law_question() -> None:
    hit = SimpleNamespace(
        point_id="1",
        payload={"chunk_id": "1", "text": "divorce divorce divorce", "title": "Special Marriage Act"},
    )
    assert (
        publishable_hits(
            [hit],
            query="How do I get a divorce in England?",
            focus_tokens={"divorce"},
            distinctive_terms=set(),
        )
        == []
    )
