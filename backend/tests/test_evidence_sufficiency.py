"""Does the retrieved evidence address the question at all?

Verification asks whether a claim follows from its source. Nothing asked
whether the source is about the question, so a corpus gap with adjacent
material produced a grounded answer to a question the corpus cannot
support: noise-pollution was answered from passages containing neither
"noise" nor "neighbouring", every claim verified against its own chunk.

The rule is the Fast lane's, called rather than copied. The two lanes have
drifted apart four times in this project, and a second relevance floor is
how that happens a fifth.
"""

from __future__ import annotations

import pytest

from app.agents.publication import evidence_addresses_the_question


class _Hit:
    def __init__(self, text: str) -> None:
        self.payload = {"chunk_id": "c", "title": "t", "text": text}
        self.point_id = "p"
        self.reranker_score = 1.0


NOISE_QUESTION = "What can be done about noise from a neighbouring factory?"


class TestACorpusGapIsRefused:
    def test_passages_about_something_else_do_not_address_the_question(self) -> None:
        """The measured case. Every one of these is real corpus material and
        none of it is about noise."""
        hits = [
            _Hit("The Magistrate may order the removal of a public nuisance under this section."),
            _Hit("Any police officer may without an order from a Magistrate arrest any person."),
            _Hit("The State Government may make rules for the conduct of inquiries."),
        ]

        assert not evidence_addresses_the_question(
            NOISE_QUESTION, hits, {"noise", "neighbouring"}
        )

    def test_a_passage_that_does_address_it_is_enough(self) -> None:
        """One is enough: the question is whether the corpus covers this at
        all, not how well."""
        hits = [
            _Hit("The State Government may make rules for the conduct of inquiries."),
            _Hit(
                "No person shall cause noise exceeding the ambient standards, and a "
                "complaint about noise from a neighbouring premises may be made to "
                "the authority."
            ),
        ]

        assert evidence_addresses_the_question(
            NOISE_QUESTION, hits, {"noise", "neighbouring"}
        )


class TestItFailsClosed:
    def test_no_hits_does_not_address_the_question(self) -> None:
        assert not evidence_addresses_the_question("anything at all", [], set())

    def test_a_question_naming_no_subject_is_refused(self) -> None:
        """"Is it?" has nothing a passage could be relevant *to*.

        Retrieval still returns its nearest neighbours, and every relevance
        test downstream would be vacuously satisfied by a query with no
        content words at all.

        The first version of this test used "what about that?", which keeps
        "about" as a focus token -- so the refusal came from the coverage
        floor and the no-focus-tokens branch went untested. Verified: this
        query yields an empty focus set and that one does not.
        """
        from app.services.fast_research import _focus_tokens

        assert _focus_tokens("is it?") == set(), "fixture no longer has an empty focus set"

        # A passage whose text would clear any floor, so only the empty
        # focus set can be what refuses it.
        generous = _Hit("is it " * 40)
        assert not evidence_addresses_the_question("is it?", [generous], set())


class TestWhatItDoesNotClaimToSolve:
    def test_right_topic_wrong_sub_topic_still_passes(self) -> None:
        """Stated, because the limit matters more than the capability.

        The corpus holds the POSH committee-constitution advisory and not
        the complaint pathway. Asked how to make a complaint, five of eight
        passages carry "harassment" and "workplace" honestly, so a lexical
        gate cannot tell that they answer a different question. This test
        exists so the limitation is recorded rather than discovered later.
        """
        question = "What is the process for a sexual harassment complaint at work?"
        hits = [
            _Hit(
                "Every employer shall constitute an Internal Committee for the "
                "prevention of sexual harassment at the workplace, and the "
                "committee shall comprise a presiding officer."
            )
        ]

        assert evidence_addresses_the_question(question, hits, {"harassment"})


class TestTheRuleIsTheFastLanes:
    def test_it_calls_publishable_hits_rather_than_reimplementing_it(self) -> None:
        """A second copy of the floor is how the lanes drift.

        Asserted structurally: the constants live in one module and this
        one must not define its own.
        """
        import inspect

        from app.agents import publication

        source = inspect.getsource(publication)
        assert "publishable_hits" in source
        assert "COVERAGE_FLOOR" not in source, (
            "the coverage floor has been copied into the publication rules; "
            "it must stay in fast_research so both lanes move together"
        )


class TestTheRecordedFindingIsHonoured:
    """Retrieval decides it; response generation must act on it.

    The finding is computed where the query and the passages are in hand
    and recorded in state. A publication path that does not read it leaves
    the gate switched off while every unit test of the gate itself still
    passes.
    """

    @staticmethod
    def _state(*, addresses: bool | None) -> dict:
        from app.schemas.agents import ClaimVerification, VerificationResult

        class _H:
            payload = {
                "chunk_id": "c1",
                "title": "Act",
                "source_type": "act",
                "text": "Noise exceeding the ambient standard is prohibited.",
                "page_start": 1,
                "page_end": 1,
            }
            point_id = "p"
            reranker_score = 1.0

        state: dict = {
            "role": "citizen",
            "retrieved_chunks": [_H()],
            "verification_result": VerificationResult(
                score=1.0,
                supported_claims=1,
                total_claims=1,
                claims=[
                    ClaimVerification(
                        claim="Noise is regulated [SRC:c1]",
                        chunk_id="c1",
                        verdict="yes",
                        category="direct_answer",
                    )
                ],
            ),
            "agent_trace": [],
        }
        if addresses is not None:
            state["evidence_addresses_question"] = addresses
        return state

    def test_a_false_finding_suppresses_a_publishable_answer(self) -> None:
        from app.agents.response_generation import response_generation_node
        from app.services.generation import INSUFFICIENT_EVIDENCE

        result = response_generation_node(self._state(addresses=False))

        assert result["final_answer"] == INSUFFICIENT_EVIDENCE

    def test_a_true_finding_leaves_it_alone(self) -> None:
        from app.agents.response_generation import response_generation_node
        from app.services.generation import INSUFFICIENT_EVIDENCE

        result = response_generation_node(self._state(addresses=True))

        assert result["final_answer"] != INSUFFICIENT_EVIDENCE

    def test_an_absent_finding_does_not_suppress(self) -> None:
        """Only an explicit False refuses.

        A path that never recorded the finding is not evidence that the
        corpus lacks coverage, and treating absence as refusal would make
        every future caller abstain by omission.
        """
        from app.agents.response_generation import response_generation_node
        from app.services.generation import INSUFFICIENT_EVIDENCE

        result = response_generation_node(self._state(addresses=None))

        assert result["final_answer"] != INSUFFICIENT_EVIDENCE


class TestItJudgesTheQuestionTheUserAsked:
    """Not the query retrieval ended up running.

    The retrieval node broadens a query on its fallback path, appending
    procedure language to widen the search. Judging coverage against that
    broadened string adds focus tokens the passages cannot carry, so the
    floor rejects every one of them.

    Measured on art19-free-speech: publication said publish, with 18
    distinct claims and a 0.556 support ratio, and this gate suppressed it
    to a 15-word refusal. Passing the user's question instead produced a
    304-word answer with no retries.

    The offline probe missed it because it used the original wording -- the
    harness measured one input and the pipeline ran another, which is the
    mismatch this project keeps repeating.
    """

    def test_a_broadened_query_rejects_passages_the_original_accepts(self) -> None:
        original = "What limits can the government place on freedom of speech?"
        broadened = (
            original
            + " procedure complaint registration general diary station officer"
            + " application filing process steps"
        )
        # Carries all five of the original question's focus terms, so it
        # clears the no-rare-term floor of 0.45 outright. An earlier version
        # used the Article 19(2) text, which scores 0.400 -- below the floor
        # for the original query too, so the test failed on correct code and
        # demonstrated nothing.
        hits = [
            _Hit(
                "The government may place limits on the freedom of speech by "
                "imposing reasonable restrictions in the interests of public "
                "order, decency or morality."
            )
        ]

        assert evidence_addresses_the_question(original, hits, set())
        assert not evidence_addresses_the_question(broadened, hits, set()), (
            "the fixture no longer demonstrates the failure; pick a broadening "
            "that actually dilutes coverage below the floor"
        )

    def test_the_node_passes_the_users_question(self) -> None:
        """Structural, because the broadening happens deep in a fallback
        path that is awkward to force from a unit test -- but the call site
        is unambiguous."""
        import inspect

        from app.agents import retrieval_agent

        source = inspect.getsource(retrieval_agent)
        assert 'evidence_addresses_the_question(\n            str(state.get("query") or query)' in source, (
            "the sufficiency gate is no longer judging state['query']; if it "
            "judges the broadened retrieval query it rejects everything"
        )
