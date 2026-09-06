"""When a verified result is worth publishing.

This replaces a gate that abstained on `verification.score < 0.5`. That
score is a ratio -- verified claims over all claims attempted -- so the
gate punished thoroughness: a broad question generates more claims, more
get rejected, the ratio falls, and the answer is thrown away even though
the absolute quantity of verified law is higher than a narrow question's.

Measured on 61 questions, 6 September 2026: six of the nine wrongly
refused questions had verified claims that never reached the reader.
`child-needing-care` produced ten claims that passed verification, ran for
332 seconds, and printed "insufficient evidence".
"""

from __future__ import annotations

import pytest

from app.agents.publication import MINIMUM_SUPPORT_RATIO, publication_decision
from app.schemas.agents import ClaimVerification, VerificationResult


def _result(*, yes: int, no: int, categories: list[str] | None = None) -> VerificationResult:
    categories = categories or ["direct_answer"] * yes
    claims = [
        ClaimVerification(claim=f"c{i}", chunk_id="chunk", verdict="yes", category=categories[i])
        for i in range(yes)
    ]
    claims += [
        ClaimVerification(claim=f"n{i}", chunk_id="chunk", verdict="no") for i in range(no)
    ]
    return VerificationResult(
        score=yes / max(yes + no, 1),
        supported_claims=yes,
        total_claims=yes + no,
        claims=claims,
    )


class TestThoroughnessIsNotPunished:
    def test_the_child_needing_care_case_now_publishes(self) -> None:
        """Ten verified claims, discarded because thirty were attempted.

        The exact shape measured in the 6 September run. Under the old
        ratio gate this scored 0.33 and abstained after 332 seconds.
        """
        decision = publication_decision(_result(yes=10, no=20))

        assert decision.publish
        assert decision.verified_claims == 10

    @pytest.mark.parametrize(("yes", "no"), [(4, 6), (5, 8), (4, 5), (1, 3)])
    def test_a_minority_of_survivors_still_publishes(self, yes: int, no: int) -> None:
        """Each claim was verified against its own chunk.

        Rejected siblings are not evidence against the survivors, and they
        are already excluded from publication. The old gate let them
        suppress the claims that passed.
        """
        assert publication_decision(_result(yes=yes, no=no)).publish

    def test_a_narrow_question_is_not_advantaged_over_a_broad_one(self) -> None:
        """The defect stated as a property: publishing must not depend on
        how many claims were attempted, only on what survived."""
        narrow = publication_decision(_result(yes=2, no=0))
        broad = publication_decision(_result(yes=10, no=20))

        assert narrow.publish and broad.publish
        assert broad.verified_claims > narrow.verified_claims


class TestWhatStillAbstains:
    def test_nothing_survived_verification(self) -> None:
        decision = publication_decision(_result(yes=0, no=5))

        assert not decision.publish
        assert "no claim survived" in decision.reason

    def test_wholesale_fabrication_still_abstains(self) -> None:
        """One claim out of twenty-one is not a partial answer.

        The floor is a fabrication guard, not a quality bar -- quality is
        carried by per-section confidence. But at this ratio even the claim
        that passed deserves suspicion.
        """
        decision = publication_decision(_result(yes=1, no=20))

        assert not decision.publish
        assert "fabrication" in decision.reason

    def test_an_answer_made_only_of_caveats_abstains(self) -> None:
        """Publishing it would be worse than abstaining, because a page of
        qualifications reads as an answer."""
        decision = publication_decision(
            _result(yes=3, no=1, categories=["limit", "limit", "limit"])
        )

        assert not decision.publish
        assert "caveat" in decision.reason

    def test_one_real_claim_beside_caveats_publishes(self) -> None:
        """The rule is about what is absent, not about what is present."""
        assert publication_decision(
            _result(yes=3, no=1, categories=["limit", "legal_basis", "limit"])
        ).publish

    def test_a_missing_verification_result_abstains(self) -> None:
        assert not publication_decision(None).publish


class TestTheFloorIsWhereItSays:
    def test_just_above_the_floor_publishes(self) -> None:
        result = _result(yes=1, no=3)  # 0.25
        assert result.score > MINIMUM_SUPPORT_RATIO
        assert publication_decision(result).publish

    def test_just_below_the_floor_does_not(self) -> None:
        result = _result(yes=1, no=6)  # ~0.14
        assert result.score < MINIMUM_SUPPORT_RATIO
        assert not publication_decision(result).publish

    def test_the_floor_is_far_below_the_gate_it_replaced(self) -> None:
        """0.5 was the defect. A floor anywhere near it reintroduces it."""
        assert MINIMUM_SUPPORT_RATIO <= 0.25


class TestTheRetryGateSharesThisDecision:
    def test_a_publishable_result_is_not_retried(self) -> None:
        """Retrying a result that would be published costs a whole extra
        pass. Under the old gate that is what happened to broad questions:
        child-needing-care retried twice, spent 332 seconds, and had its
        ten verified claims discarded anyway.
        """
        from app.agents.orchestrator import LegalRAGWorkflow

        state = {"verification_result": _result(yes=10, no=20), "retry_count": 0}

        assert LegalRAGWorkflow._route_after_verification(state) == "proceed"

    def test_an_unpublishable_result_is_retried(self) -> None:
        from app.agents.orchestrator import LegalRAGWorkflow

        state = {"verification_result": _result(yes=0, no=5), "retry_count": 0}

        assert LegalRAGWorkflow._route_after_verification(state) == "retry"

    def test_the_retry_bound_still_holds(self) -> None:
        from app.agents.orchestrator import LegalRAGWorkflow

        state = {"verification_result": _result(yes=0, no=5), "retry_count": 2}

        assert LegalRAGWorkflow._route_after_verification(state) == "proceed"


class TestFabricationIsScoredOnClaimsNotCitations:
    """A claim citing three sources produces three claim-marker pairs.

    `VerificationResult.score` is computed over those pairs, so a
    well-sourced claim that one source strongly entails and two merely
    touch scores 1 yes and 2 no -- and drags its own ratio down. The metric
    penalised exactly the sourcing it should reward.

    Measured 6 September: art19-free-speech had four claims pass
    verification and still abstained, because the pair ratio fell under the
    fabrication floor.
    """

    @staticmethod
    def _multi_source(supported_claims: int, unsupported_claims: int) -> VerificationResult:
        """Each supported claim cites three sources; one entails it."""
        claims: list[ClaimVerification] = []
        for index in range(supported_claims):
            claims.append(
                ClaimVerification(
                    claim=f"supported-{index}", chunk_id="a", verdict="yes",
                    category="legal_basis",
                )
            )
            claims += [
                ClaimVerification(claim=f"supported-{index}", chunk_id=chunk, verdict="no")
                for chunk in ("b", "c")
            ]
        for index in range(unsupported_claims):
            claims.append(
                ClaimVerification(claim=f"dropped-{index}", chunk_id="d", verdict="no")
            )
        pairs = len(claims)
        supported_pairs = sum(1 for c in claims if c.verdict == "yes")
        return VerificationResult(
            score=supported_pairs / pairs,
            supported_claims=supported_pairs,
            total_claims=pairs,
            claims=claims,
        )

    def test_the_pair_ratio_and_the_claim_ratio_genuinely_differ(self) -> None:
        """A guard on the fixture itself.

        If these ever coincide, every assertion below passes under either
        implementation and this class stops testing anything.
        """
        # 4 supported / 10 dropped straddles the floor: pair 0.182, claim
        # 0.286. The first version used 4/6, whose pair ratio is 0.222 --
        # already above the floor, so both implementations published and the
        # class tested nothing. This guard is what caught that.
        result = self._multi_source(supported_claims=4, unsupported_claims=10)

        assert result.score < MINIMUM_SUPPORT_RATIO, "pair ratio no longer falls below the floor"
        assert publication_decision(result).publish, "claim ratio no longer clears it"

    def test_a_well_sourced_answer_is_not_read_as_fabrication(self) -> None:
        """The art19-free-speech shape: four claims, each with two sources
        that did not individually entail it."""
        assert publication_decision(self._multi_source(4, 10)).publish

    def test_wholesale_fabrication_still_fails_on_the_claim_ratio(self) -> None:
        """One claim in twenty is fabrication however it is counted."""
        decision = publication_decision(self._multi_source(1, 19))

        assert not decision.publish
        assert "fabrication" in decision.reason

    def test_a_claim_needs_only_one_source_to_entail_it(self) -> None:
        """Requiring every cited source to entail the claim would reject
        the best-sourced claims first: the more sources a claim carries,
        the more chances it has to be marked down."""
        one_of_three = self._multi_source(supported_claims=3, unsupported_claims=0)

        assert publication_decision(one_of_three).publish
