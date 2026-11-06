"""Foreign law is refused; Indian law with a foreign connection is not."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.fast_research import publishable_hits
from app.services.question_scope import (
    OffTopicCheck,
    asks_about_foreign_law,
    off_topic_check_for,
    out_of_scope_answer,
    warm_off_topic_check,
)


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


class _Encoder:
    """Examples and the query as fixed points, so only the comparison is under test."""

    def __init__(self, query_vector: list[float], *, broken: bool = False) -> None:
        self.query_vector = query_vector
        self.broken = broken
        self.document_calls = 0

    async def embed_documents(self, texts, *, batch_size=8):
        self.document_calls += 1
        if self.broken:
            raise RuntimeError("encoder unavailable")
        from app.services.question_scope import _NOT_LEGAL_EXAMPLES

        return [
            SimpleNamespace(dense=[1.0, 0.0] if text in _NOT_LEGAL_EXAMPLES else [0.0, 1.0])
            for text in texts
        ]

    async def embed_query(self, query):
        return self.query_vector


async def test_closer_to_everyday_questions_is_off_topic() -> None:
    assert await OffTopicCheck(_Encoder([1.0, 0.0])).is_off_topic("Which shares should I buy?")


async def test_closer_to_legal_questions_is_not() -> None:
    assert not await OffTopicCheck(_Encoder([0.0, 1.0])).is_off_topic("My boss has not paid me")


async def test_a_legal_word_keeps_the_question_without_asking_the_encoder() -> None:
    encoder = _Encoder([1.0, 0.0])
    assert not await OffTopicCheck(encoder).is_off_topic("Is it illegal to sell shares this way?")
    assert encoder.document_calls == 0


async def test_a_failure_never_costs_an_answer() -> None:
    assert not await OffTopicCheck(_Encoder([1.0, 0.0], broken=True)).is_off_topic("What should I cook?")


async def test_examples_prepared_at_startup_are_not_embedded_again() -> None:
    encoder = _Encoder([0.0, 1.0])
    await warm_off_topic_check(encoder)
    assert encoder.document_calls == 1
    assert not await off_topic_check_for(encoder).is_off_topic("My boss has not paid me")
    assert encoder.document_calls == 1


async def test_a_failed_startup_preparation_is_retried_by_the_first_question() -> None:
    encoder = _Encoder([1.0, 0.0], broken=True)
    await warm_off_topic_check(encoder)
    encoder.broken = False
    assert await off_topic_check_for(encoder).is_off_topic("What should I cook?")
    assert encoder.document_calls == 2


async def test_startup_preparation_survives_having_no_encoder() -> None:
    await warm_off_topic_check(None)


async def test_with_no_encoder_a_question_is_answered_not_lost() -> None:
    assert await out_of_scope_answer("What should I cook?", None) is None


async def test_with_no_encoder_foreign_law_is_still_refused() -> None:
    assert (await out_of_scope_answer("How do I get a divorce in England?", None))[0] == "foreign_law"


@pytest.mark.parametrize("greeting", ["hi", "Hello!", "thanks", "namaste"])
async def test_a_greeting_is_not_searched_for_law(greeting: str) -> None:
    encoder = _Encoder([0.0, 1.0])
    assert await OffTopicCheck(encoder).is_off_topic(greeting)
    assert encoder.document_calls == 0
