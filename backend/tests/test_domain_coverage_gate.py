"""The domain route through the Fast lane's coverage gate.

The gate's purpose is to abstain when the corpus cannot answer. The lexical
floor achieves that but cannot bridge vocabulary, so a question asked in lay
words is retrieved correctly by BGE-M3 and then discarded. These tests pin both
halves: the route must admit an on-topic provision written in statutory words,
and must still abstain when the corpus holds nothing on the subject.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.fast_research import (
    DOMAIN_COVERAGE_FLOOR,
    _domain_coverage,
    _focus_tokens,
    publishable_hits,
)
from app.services.lay_vocabulary import domain_vocabulary


def hit(title: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        payload={"title": title, "text": text, "act_name": title, "chunk_id": title},
        point_id=title,
    )


CONSUMER = hit(
    "Consumer Protection Act 2019",
    "Any consumer may file a complaint before the consumer commission alleging "
    "a defect in goods or deficiency in service or an unfair trade practice.",
)
CHILD_PROCEDURE = hit(
    "BNSS 2023 section 94",
    "Procedure on a report of a missing child, including immediate registration "
    "and search by the officer in charge of the police station.",
)


class TestDomainVocabulary:
    def test_lay_consumer_question_identifies_its_domain(self):
        tokens, domains = domain_vocabulary("the shop refused to replace my broken phone")
        assert domains == ("consumer",)
        assert "deficiency" in tokens

    def test_question_outside_every_bridge_contributes_nothing(self):
        tokens, domains = domain_vocabulary("my pet dog is missing what do i do")
        assert domains == ()
        assert tokens == frozenset()


class TestDomainCoverage:
    def test_on_topic_provision_uses_the_domain_vocabulary(self):
        tokens, _ = domain_vocabulary("the shop refused to replace my broken phone")
        assert _domain_coverage(tokens, CONSUMER.payload) >= DOMAIN_COVERAGE_FLOOR

    def test_unrelated_provision_does_not(self):
        tokens, _ = domain_vocabulary("the shop refused to replace my broken phone")
        assert _domain_coverage(tokens, CHILD_PROCEDURE.payload) < DOMAIN_COVERAGE_FLOOR

    def test_no_domain_means_no_coverage(self):
        assert _domain_coverage(frozenset(), CONSUMER.payload) == 0.0


class TestGate:
    QUERY = "the shop refused to replace my broken phone"

    def test_lexical_floor_alone_discards_the_correct_provision(self):
        """The failure this route exists to fix. If this ever passes, the
        premise is gone and the route is unnecessary."""
        kept = publishable_hits(
            [CONSUMER],
            query=self.QUERY,
            focus_tokens=_focus_tokens(self.QUERY),
            distinctive_terms=set(),
        )
        assert kept == []

    def test_domain_route_admits_the_correct_provision(self):
        tokens, _ = domain_vocabulary(self.QUERY)
        kept = publishable_hits(
            [CONSUMER],
            query=self.QUERY,
            focus_tokens=_focus_tokens(self.QUERY),
            distinctive_terms=set(),
            domain_tokens=tokens,
        )
        assert kept == [CONSUMER]

    def test_domain_route_still_abstains_on_an_unrelated_corpus(self):
        """The property the gate exists for, and the one a dense-similarity
        floor would have destroyed: nearest neighbours are not coverage."""
        tokens, _ = domain_vocabulary(self.QUERY)
        kept = publishable_hits(
            [CHILD_PROCEDURE],
            query=self.QUERY,
            focus_tokens=_focus_tokens(self.QUERY),
            distinctive_terms=set(),
            domain_tokens=tokens,
        )
        assert kept == []

    def test_query_with_no_bridge_sees_the_gate_unchanged(self):
        query = "my pet dog is missing what do i do"
        tokens, _ = domain_vocabulary(query)
        for domain in (frozenset(), tokens):
            assert (
                publishable_hits(
                    [CHILD_PROCEDURE],
                    query=query,
                    focus_tokens=_focus_tokens(query),
                    distinctive_terms=set(),
                    domain_tokens=domain,
                )
                == []
            )
