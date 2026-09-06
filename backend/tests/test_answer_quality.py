"""The instrument has to be trustworthy before its readings mean anything.

Each test here names the specific wrong number the metric would report if
the behaviour under test were dropped, because a quality metric that fails
silently is worse than no metric: it certifies.
"""

from __future__ import annotations

import pytest

from app.evaluation.answer_quality import (
    GroundExpectation,
    abstained,
    assess_answer,
    currency_assessment,
    ground_coverage,
    reading_grade,
    unsupported_claims,
)
from app.schemas.agents import AgentCitation, ClaimVerification, VerificationResult
from app.services.generation import INSUFFICIENT_EVIDENCE


class _Hit:
    """The shape retrieval returns, reduced to what the metrics read."""

    def __init__(self, payload: dict, point_id: str = "p") -> None:
        self.payload = payload
        self.point_id = point_id
        self.reranker_score = 1.0


def _citation(chunk_id: str) -> AgentCitation:
    return AgentCitation(
        number=1,
        chunk_id=chunk_id,
        title="t",
        source_type="act",
        page_start=1,
        page_end=1,
        excerpt="e",
    )


def _state(
    *,
    answer: str = "An answer.",
    claims: list[ClaimVerification] | None = None,
    hits: list[_Hit] | None = None,
    citations: list[AgentCitation] | None = None,
) -> dict:
    claims = claims or []
    return {
        "final_answer": answer,
        "retrieved_chunks": hits or [],
        "citations": citations or [],
        "verification_result": VerificationResult(
            score=1.0,
            supported_claims=sum(1 for c in claims if c.verdict == "yes"),
            total_claims=len(claims),
            claims=claims,
        ),
    }


class TestAbstentionIsReadFromTheSentinel:
    def test_the_sentinel_is_an_abstention(self) -> None:
        assert abstained(_state(answer=INSUFFICIENT_EVIDENCE))

    def test_an_empty_answer_is_an_abstention(self) -> None:
        assert abstained(_state(answer="   "))

    def test_an_answer_citing_nothing_is_still_an_answer(self) -> None:
        """The tempting shortcut -- no citations means abstained -- is wrong.

        An answer can cite nothing and still be published prose. Reading
        abstention off the citation list would score every such run as a
        correct abstention and hide a real failure.
        """
        assert not abstained(_state(answer="Section 35 permits this.", citations=[]))


class TestUnsupportedClaimsEnforceTheStandingRule:
    def test_a_published_claim_outside_the_retrieved_set_is_caught(self) -> None:
        state = _state(
            claims=[ClaimVerification(claim="c", chunk_id="ghost", verdict="yes")],
            hits=[_Hit({"chunk_id": "real"})],
        )

        found = unsupported_claims(state)

        assert [c.chunk_id for c in found] == ["ghost"]

    def test_a_published_claim_inside_the_retrieved_set_is_clean(self) -> None:
        state = _state(
            claims=[ClaimVerification(claim="c", chunk_id="real", verdict="yes")],
            hits=[_Hit({"chunk_id": "real"})],
        )

        assert unsupported_claims(state) == []

    @pytest.mark.parametrize("verdict", ["no", "partial"])
    def test_verification_doing_its_job_is_not_a_violation(self, verdict: str) -> None:
        """A rejected claim never reaches the reader.

        Counting every non-``yes`` claim as unsupported would report a
        violation on exactly the runs where verification worked, and the
        obvious way to make the metric green would be to stop rejecting
        claims -- which is the one thing that must never happen.
        """
        state = _state(
            claims=[ClaimVerification(claim="c", chunk_id="ghost", verdict=verdict)],
            hits=[_Hit({"chunk_id": "real"})],
        )

        assert unsupported_claims(state) == []


class TestCurrencyIsCheckedAgainstTheResolver:
    def test_a_superseded_act_that_is_not_disclosed_fails(self) -> None:
        payload = {
            "chunk_id": "c1",
            "act_name": "The Indian Penal Code, 1860",
            "is_superseded": True,
            "replaced_by": "The Bharatiya Nyaya Sanhita, 2023",
        }
        state = _state(
            answer="Theft is punishable under section 378.",
            hits=[_Hit(payload)],
            citations=[_citation("c1")],
        )

        assessment = currency_assessment(state)

        assert assessment.required == 1
        assert assessment.satisfied == 0
        assert not assessment.correct

    def test_the_same_act_disclosed_passes(self) -> None:
        payload = {
            "chunk_id": "c1",
            "act_name": "The Indian Penal Code, 1860",
            "is_superseded": True,
            "replaced_by": "The Bharatiya Nyaya Sanhita, 2023",
        }
        state = _state(
            answer=(
                "Theft is punishable under section 378.\n\n## Source currency\n\n"
                "The Indian Penal Code, 1860 is no longer in force; it was replaced "
                "by the Bharatiya Nyaya Sanhita, 2023."
            ),
            hits=[_Hit(payload)],
            citations=[_citation("c1")],
        )

        assert currency_assessment(state).correct

    def test_a_vague_hedge_does_not_count_as_disclosure(self) -> None:
        """"Some sources may be outdated" is not a currency label.

        Without the Act-name match, that sentence would satisfy the metric
        for every repealed source in the corpus at once, and the metric
        would go green precisely when the answer is least useful.
        """
        payload = {
            "chunk_id": "c1",
            "act_name": "The Indian Penal Code, 1860",
            "is_superseded": True,
            "replaced_by": "The Bharatiya Nyaya Sanhita, 2023",
        }
        state = _state(
            answer="Theft is an offence. Some sources may be no longer in force.",
            hits=[_Hit(payload)],
            citations=[_citation("c1")],
        )

        assert not currency_assessment(state).correct

    def test_an_abstention_carries_no_currency_obligation(self) -> None:
        payload = {"chunk_id": "c1", "act_name": "X", "is_superseded": True}
        state = _state(
            answer=INSUFFICIENT_EVIDENCE, hits=[_Hit(payload)], citations=[_citation("c1")]
        )

        assert currency_assessment(state).required == 0


class TestGroundCoverageCountsGroundsNotWords:
    def test_alternative_spellings_of_one_ground_count_once(self) -> None:
        expectations = [GroundExpectation("cognizable", ("cognizable", "cognisable"))]

        coverage, missed = ground_coverage("a cognisable offence", expectations)

        assert coverage == 1.0
        assert missed == ()

    def test_a_missed_ground_is_named_not_just_counted(self) -> None:
        expectations = [
            GroundExpectation("cognizable", ("cognizable offence",)),
            GroundExpectation("proclaimed offender", ("proclaimed offender",)),
        ]

        coverage, missed = ground_coverage("a cognizable offence", expectations)

        assert coverage == 0.5
        assert missed == ("proclaimed offender",)

    def test_no_expectations_scores_nothing_rather_than_one(self) -> None:
        """An unauthored item must not report perfect coverage.

        Returning 1.0 for an empty expectation list would let the aggregate
        rise every time someone added a question without authoring its
        grounds -- improvement by omission.
        """
        assert ground_coverage("anything at all", []) == (None, ())


class TestReadingGrade:
    def test_short_plain_sentences_score_lower_than_dense_ones(self) -> None:
        plain = reading_grade("You can ask the police for help. They must write it down.")
        dense = reading_grade(
            "Notwithstanding the aforementioned statutory provisions, the "
            "investigating authority retains discretionary jurisdiction to "
            "determine the appropriateness of registering the information."
        )

        assert plain is not None and dense is not None
        assert plain < dense

    def test_a_numbered_list_marker_is_not_a_sentence_end(self) -> None:
        """"1." looks exactly like the end of a sentence to a regex.

        This is not hypothetical scaffolding: the citizen role renders its
        next steps as a numbered list, so it is the one answer shape where
        reading level matters most. Left unstripped, each marker counts as
        a sentence end, which shortens the apparent sentence length and
        makes a long procedural instruction read as easier than it is --
        the metric would understate difficulty precisely where a citizen
        is most likely to be lost.
        """
        step = (
            "Go to the nearest police station and ask the officer on duty to "
            "record your complaint in writing"
        )
        numbered = f"## What to do\n\n1. {step}\n2. {step}\n3. {step}"
        same_text_unmarked = f"{step} {step} {step}"

        graded = reading_grade(numbered)

        assert graded is not None
        # One run-on sentence either way, so the markers must have added no
        # sentence ends at all.
        assert graded == pytest.approx(reading_grade(same_text_unmarked), abs=1.5)

    def test_an_empty_answer_has_no_grade(self) -> None:
        assert reading_grade("") is None


class TestAssembly:
    def test_an_expected_abstention_is_scored_correct_and_ungraded(self) -> None:
        state = _state(answer=INSUFFICIENT_EVIDENCE)

        quality = assess_answer(
            state,
            item_id="contract-elements",
            role="citizen",
            expectation="abstain",
            grounds=[{"name": "offer", "any_of": ["offer"]}],
        )

        assert quality.abstention_correct
        # Not 0.0: a correct abstention must not be scored as a bad answer,
        # or the aggregate punishes the system for following its own rule.
        assert quality.ground_coverage is None
        assert quality.reading_grade is None

    def test_answering_when_abstention_was_expected_is_incorrect(self) -> None:
        quality = assess_answer(
            _state(answer="The essential elements are offer and acceptance."),
            item_id="contract-elements",
            role="citizen",
            expectation="abstain",
        )

        assert not quality.abstention_correct

    def test_abstaining_when_an_answer_was_expected_is_incorrect(self) -> None:
        quality = assess_answer(
            _state(answer=INSUFFICIENT_EVIDENCE),
            item_id="arrest-grounds",
            role="citizen",
            expectation="answer",
        )

        assert not quality.abstention_correct
