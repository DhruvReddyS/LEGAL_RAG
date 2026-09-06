"""Each rule here exists because the alternative flatters a weak section.

A single confidence number for a whole answer is the thing this replaces:
an answer can state the governing provision from the Sanhita and then draw
its practical steps from one circular, and 0.86 across the whole thing tells
the reader nothing about which half to rely on.
"""

from __future__ import annotations

import pytest

from app.services.section_confidence import (
    AuthorityTier,
    ConfidenceLabel,
    authority_tier,
    section_confidence,
)

IN_FORCE = {"is_current": True}


def _grade(payloads: dict[str, dict], *, claims: int = 2):
    return section_confidence("next_step", list(payloads), payloads, claim_count=claims)


class TestOneSourceIsNeverStrong:
    def test_a_single_statute_is_moderate_not_strong(self) -> None:
        """However good the source, one passage read one way is how a
        confident wrong answer gets made."""
        graded = _grade({"a": {"document_type": "bare_act", **IN_FORCE}})

        assert graded.label is ConfidenceLabel.MODERATE
        assert "single source" in graded.reason

    def test_two_corroborating_sources_reach_strong(self) -> None:
        graded = _grade({
            "a": {"document_type": "bare_act", **IN_FORCE},
            "b": {"document_type": "judgment", **IN_FORCE},
        })

        assert graded.label is ConfidenceLabel.STRONG


class TestGuidanceAloneCannotEstablishTheLaw:
    def test_many_circulars_are_still_limited(self) -> None:
        """Three circulars agreeing establish what an administrator believed
        the law to be, not what it is. Counting them as corroboration is how
        a departmental practice becomes a legal proposition."""
        graded = _grade({
            "a": {"document_type": "sop_or_circular", **IN_FORCE},
            "b": {"document_type": "sop_or_circular", **IN_FORCE},
            "c": {"document_type": "manual", **IN_FORCE},
        })

        assert graded.label is ConfidenceLabel.LIMITED
        assert "guidance" in graded.reason

    def test_guidance_beside_a_statute_is_fine(self) -> None:
        """The rule is about what is absent, not about what is present."""
        graded = _grade({
            "a": {"document_type": "bare_act", **IN_FORCE},
            "b": {"document_type": "sop_or_circular", **IN_FORCE},
        })

        assert graded.label is ConfidenceLabel.STRONG


class TestUnverifiedCurrencyCapsTheSection:
    def test_an_unverified_source_prevents_strong(self) -> None:
        """"Probably still in force" is not a foundation.

        The whole currency design exists so this stays visible. Letting it
        average away here would undo it at the last step.
        """
        graded = _grade({
            "a": {"document_type": "bare_act", **IN_FORCE},
            "b": {"document_type": "judgment"},  # no currency information
        })

        assert graded.currency_unverified
        assert graded.label is ConfidenceLabel.MODERATE
        assert "unverified" in graded.reason

    def test_the_same_section_with_verified_currency_is_strong(self) -> None:
        graded = _grade({
            "a": {"document_type": "bare_act", **IN_FORCE},
            "b": {"document_type": "judgment", **IN_FORCE},
        })

        assert not graded.currency_unverified
        assert graded.label is ConfidenceLabel.STRONG


class TestAuthorityTier:
    @pytest.mark.parametrize(
        ("document_type", "expected"),
        [
            ("bare_act", AuthorityTier.PRIMARY),
            ("amendment", AuthorityTier.PRIMARY),
            ("rules_or_regulations", AuthorityTier.PRIMARY),
            ("judgment", AuthorityTier.DECISION),
            ("sop_or_circular", AuthorityTier.GUIDANCE),
            ("manual", AuthorityTier.GUIDANCE),
            ("commentary", AuthorityTier.SECONDARY),
        ],
    )
    def test_the_stored_type_decides(self, document_type: str, expected) -> None:
        assert authority_tier({"document_type": document_type}) is expected

    # Every source_type actually present in this corpus, counted from the
    # chunk files, with its chunk mass. Written from the data rather than
    # from what a classifier might plausibly emit: the first version of this
    # test asserted "act", "judgment" and "advisory", none of which the
    # corpus writes, so it passed while the Constitution and every Supreme
    # Court judgment fell through to SECONDARY.
    @pytest.mark.parametrize(
        ("source_type", "expected"),
        [
            ("ACT", AuthorityTier.PRIMARY),                     # 7285 chunks
            ("SUPREME_COURT_JUDGMENT", AuthorityTier.DECISION), # 7040
            ("RULE", AuthorityTier.PRIMARY),                    # 3750
            ("CONSTITUTION", AuthorityTier.PRIMARY),            # 2023
            ("LAW_COMMISSION_REPORT", AuthorityTier.SECONDARY), # 1421
            ("GOVERNMENT_GUIDANCE", AuthorityTier.GUIDANCE),    # 1258
            ("POLICE_MANUAL", AuthorityTier.GUIDANCE),          # 848
            ("ORDER", AuthorityTier.GUIDANCE),                  # 259
            ("HIGH_COURT_JUDGMENT", AuthorityTier.DECISION),    # 205
            ("GOVERNMENT_HANDBOOK", AuthorityTier.GUIDANCE),    # 86
            ("NOTIFICATION", AuthorityTier.PRIMARY),            # 43
            ("AMENDMENT", AuthorityTier.PRIMARY),               # 36
        ],
    )
    def test_an_older_point_falls_back_to_source_type(self, source_type, expected) -> None:
        """An index built before the classifier existed must still grade.

        The v2 index carries no document_type at all -- 9,817 of 9,817
        sampled chunks have it as null -- so on that index this fallback is
        the only signal there is. Getting it wrong does not fail loudly; it
        caps every section at limited and makes the whole grading useless
        on the corpus currently deployed.
        """
        assert authority_tier({"source_type": source_type}) is expected

    def test_a_law_commission_report_is_never_primary_authority(self) -> None:
        """The largest single uncurated item in this corpus is one.

        948 chunks of the Law Commission's review of the Evidence Act. It
        recommends what the law should be; treating it as what the law is
        would let a section reach strong on a recommendation that was never
        enacted.
        """
        assert authority_tier({"source_type": "LAW_COMMISSION_REPORT"}) is AuthorityTier.SECONDARY
        assert authority_tier({"document_type": "commentary"}) is AuthorityTier.SECONDARY

    def test_an_unknown_type_is_secondary_not_primary(self) -> None:
        """Unknown must not be generous. Guessing primary would let an
        unclassified passage carry a section to strong on its own."""
        assert authority_tier({}) is AuthorityTier.SECONDARY
        assert authority_tier({"document_type": "something_new"}) is AuthorityTier.SECONDARY


class TestDegenerateInput:
    def test_a_section_whose_sources_cannot_be_resolved_is_limited(self) -> None:
        graded = section_confidence("limit", ["ghost"], {}, claim_count=1)

        assert graded.label is ConfidenceLabel.LIMITED
        assert graded.source_count == 0

    def test_repeated_chunk_ids_count_once(self) -> None:
        """Citing the same passage twice is not corroboration.

        Without the de-duplication a section resting on one source reaches
        strong by repeating it, which is the easiest possible way to fake
        the signal.
        """
        payloads = {"a": {"document_type": "bare_act", **IN_FORCE}}
        graded = section_confidence("legal_basis", ["a", "a", "a"], payloads, claim_count=3)

        assert graded.source_count == 1
        assert graded.label is ConfidenceLabel.MODERATE


class TestItReachesTheAnswer:
    """The grading is worthless if nothing produces it.

    Wiring a new field through a LangGraph state is exactly the kind of
    change that type-checks, passes every unit test, and silently yields an
    empty list forever, because every consumer reads it with .get().
    """

    @pytest.mark.asyncio
    async def test_a_published_answer_carries_a_grade_per_section(self) -> None:
        from app.agents.orchestrator import LegalRAGWorkflow
        from tests.test_answer_harness_contract import VerifyingFakeLLM
        from tests.test_deep_pipeline_telemetry import InstrumentedFakeRetrieval

        state = await LegalRAGWorkflow(
            InstrumentedFakeRetrieval(),  # type: ignore[arg-type]
            VerifyingFakeLLM(),  # type: ignore[arg-type]
        ).run(query="When must an FIR be registered?", role="citizen", case_id=None, history=[])

        grades = state.get("section_confidence")

        assert grades, "the workflow published an answer but graded no section"
        for grade in grades:
            assert grade["section"], "a grade must name the section it belongs to"
            assert grade["confidence"] in {"strong", "moderate", "limited"}
            assert grade["reason"], "a grade without a reason cannot be acted on"
            assert grade["sources"] >= 1, (
                f"{grade['section']!r} was graded with no source. That row "
                "belongs to a section the answer does not contain: an empty "
                "category grades as 'limited', which puts a confidence "
                "rating in front of the reader for content that is not there."
            )

        # The decisive check: exactly the headings the answer actually has.
        headings = {
            line.removeprefix("## ").strip()
            for line in str(state["final_answer"]).splitlines()
            if line.startswith("## ")
        }
        assert {grade["section"] for grade in grades} == headings - {"Source currency"}

    @pytest.mark.asyncio
    async def test_an_abstention_grades_nothing(self) -> None:
        """There are no published sections to grade, and emitting a
        'limited' row would put a confidence rating in front of a reader
        for content the answer does not contain."""
        from app.agents.orchestrator import LegalRAGWorkflow
        from tests.test_deep_pipeline_telemetry import (
            InstrumentedFakeLLM,
            InstrumentedFakeRetrieval,
        )

        # This fake verifies nothing, so the run abstains.
        state = await LegalRAGWorkflow(
            InstrumentedFakeRetrieval(),  # type: ignore[arg-type]
            InstrumentedFakeLLM(),  # type: ignore[arg-type]
        ).run(query="When must an FIR be registered?", role="citizen", case_id=None, history=[])

        assert state.get("section_confidence") == []
