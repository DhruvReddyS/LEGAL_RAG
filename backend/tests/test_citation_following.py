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

from unittest.mock import AsyncMock

import pytest

from app.services.citation_following import (
    MAX_FOLLOWED,
    MIN_CITATIONS,
    implementation_provisions_for_query,
    provisions_worth_following,
)
from app.services.retrieval import (
    HybridRetrievalService,
    RetrievalFilters,
    RetrievalHit,
    RetrievalTarget,
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


class TestImplementationBridge:
    @pytest.mark.parametrize(
        ("question", "expected"),
        [
            ("What is default bail?", ("BNSS", "187")),
            ("Which law now governs the offence of theft?", ("BNS", "303")),
            (
                "Must the grounds of arrest be communicated to the arrested person?",
                ("BNSS", "47"),
            ),
            (
                "Which law now governs arrest without a warrant?",
                ("BNSS", "35"),
            ),
            (
                "Which law now governs evidence in criminal trials?",
                ("BSA", "1"),
            ),
        ],
    )
    def test_measured_vocabulary_gap_reaches_its_implementation(
        self,
        question: str,
        expected: tuple[str, str],
    ) -> None:
        assert expected in [
            provision.key for provision in implementation_provisions_for_query(question)
        ]

    @pytest.mark.parametrize(
        "question",
        [
            "What evidence is needed at a criminal trial?",
            "How do I report a lost phone?",
            "Can bail be cancelled?",
            # Arrest questions that are not about a warrantless arrest or the
            # reasons for one. "Without a warrant" used to be excluded as well;
            # it is now a positive, because BNSS s.35 governs it and an
            # already-retrieved hit is promoted rather than fetched again.
            "How is an arrest warrant executed by the police?",
            "Can a court issue a warrant of arrest against a witness?",
        ],
    )
    def test_adjacent_questions_do_not_trigger_a_bridge(self, question: str) -> None:
        assert implementation_provisions_for_query(question) == []

    # Reworded questions a person would actually type, in vocabulary the
    # golden set does not use. The first version of the bridges matched the
    # evaluation wording and reached one of the first ten of these.
    @pytest.mark.parametrize(
        ("question", "expected"),
        [
            ("My brother has been in jail 90 days and no chargesheet was filed, can he get out?", ("BNSS", "187")),
            ("Police kept my son 60 days without filing a charge sheet, is he entitled to release?", ("BNSS", "187")),
            ("right to bail if investigation is not completed in time", ("BNSS", "187")),
            ("Is stealing still punished under the IPC or some new code?", ("BNS", "303")),
            ("someone stole my phone, which law covers this now", ("BNS", "303")),
            ("Do the police have to tell me why they are arresting me?", ("BNSS", "47")),
            ("police detained me and did not explain why", ("BNSS", "47")),
            ("When can police make an arrest without a warrant?", ("BNSS", "35")),
            ("Under the new code, can cops arrest without a warrant?", ("BNSS", "35")),
            ("Does the Indian Evidence Act 1872 still apply in criminal cases?", ("BSA", "1")),
            ("What replaced the Evidence Act?", ("BSA", "1")),
            ("which evidence law applies to trials after July 2024", ("BSA", "1")),
        ],
    )
    def test_reworded_questions_reach_the_same_provision(
        self, question: str, expected: tuple[str, str]
    ) -> None:
        assert expected in [p.key for p in implementation_provisions_for_query(question)]

    @pytest.mark.parametrize(
        ("question", "not_expected"),
        [
            ("How do I apply for anticipatory bail?", ("BNSS", "187")),
            ("What is the procedure for regular bail in a sessions court?", ("BNSS", "187")),
            ("Is receiving stolen property an offence?", ("BNS", "303")),
            ("What is the punishment for robbery?", ("BNS", "303")),
            ("Can a civil court issue an arrest warrant for unpaid debt?", ("BNSS", "35")),
            ("How do I present WhatsApp chats as evidence in a divorce case?", ("BSA", "1")),
            ("How is a confession recorded before a magistrate?", ("BSA", "1")),
        ],
    )
    def test_neighbouring_topics_do_not_borrow_a_provision(
        self, question: str, not_expected: tuple[str, str]
    ) -> None:
        assert not_expected not in [p.key for p in implementation_provisions_for_query(question)]

    # A repealed section named in the question goes through the official
    # concordance, so every one is bridged, not only those someone measured.
    @pytest.mark.parametrize(
        ("question", "expected"),
        [
            ("Is section 41 CrPC still the law for warrantless arrests?", ("BNSS", "35")),
            ("What is the BNSS equivalent of CrPC section 41?", ("BNSS", "35")),
            ("IPC 379 punishment", ("BNS", "303")),
            ("what happened to s. 167 Cr.P.C.", ("BNSS", "187")),
            ("Is section 32 of the Indian Evidence Act still valid for dying declarations?", ("BSA", "26")),
        ],
    )
    def test_a_named_repealed_section_follows_the_concordance(
        self, question: str, expected: tuple[str, str]
    ) -> None:
        assert expected in [p.key for p in implementation_provisions_for_query(question)]

    def test_a_section_the_concordance_did_not_carry_forward_reaches_nothing(self) -> None:
        # Sedition, IPC s.124A, has no successor. Inventing one is the failure
        # this must never have.
        assert implementation_provisions_for_query("Is IPC section 124A still in force?") == []

    def test_the_year_in_an_act_name_is_not_read_as_a_section(self) -> None:
        # "1973" must not be read as CrPC s.197, which the concordance would
        # happily carry to BNSS s.218 -- sanction to prosecute, a provision the
        # question never mentioned.
        keys = [
            p.key
            for p in implementation_provisions_for_query(
                "Code of Criminal Procedure, 1973 section 41 arrest powers"
            )
        ]
        assert ("BNSS", "35") in keys
        assert ("BNSS", "218") not in keys

    @pytest.mark.asyncio
    async def test_an_exact_candidate_is_promoted_without_another_qdrant_call(
        self,
    ) -> None:
        service = object.__new__(HybridRetrievalService)
        service.client = AsyncMock()
        candidate = RetrievalHit(
            point_id="bnss-187",
            payload={
                "chunk_id": "bnss-187",
                "act_name": "THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023",
                "section": "187",
            },
            dense_score=0.8,
            sparse_score=1.2,
            fused_score=0.7,
            reranker_score=0.7,
        )

        promoted = await service.fetch_followed_provisions(
            [candidate],
            target=RetrievalTarget(
                collection_name="test",
                filters=RetrievalFilters(corpus_tiers=[]),
            ),
            query="What is default bail?",
        )

        assert len(promoted) == 1
        assert promoted[0].point_id == candidate.point_id
        assert (
            promoted[0].payload["retrieval_enrichment_relation"]
            == "implementation_bridge"
        )
        service.client.scroll.assert_not_awaited()


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
