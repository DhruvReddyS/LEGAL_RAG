"""Repealed law may say what the law was. It must not read as what the law is."""

from __future__ import annotations

import pytest

from app.agents.response_generation import response_generation_node
from app.schemas.agents import ClaimVerification, VerificationResult
from app.services.currency import CurrencyStatus, resolve_currency
from app.services.repeal_labels import repeal_notice
from app.services.retrieval import RetrievalHit
from app.services.section_confidence import ConfidenceLabel, section_confidence


def _hit(chunk_id: str, title: str, *, section: str = "41", **payload) -> RetrievalHit:
    return RetrievalHit(
        point_id=chunk_id,
        payload={
            "chunk_id": chunk_id,
            "title": title,
            "act_name": title,
            "source_type": "act",
            "document_type": "bare_act",
            "page_start": 1,
            "page_end": 1,
            "section": section,
            "text": "Passage text.",
            **payload,
        },
        dense_score=0.5,
        sparse_score=None,
        fused_score=0.5,
        reranker_score=None,
    )


def _generate(hit: RetrievalHit, claim: str) -> str:
    return response_generation_node(
        {
            "draft_answer": f"{claim} [SRC:{hit.payload['chunk_id']}]",
            "retrieved_chunks": [hit],
            "verification_result": VerificationResult(
                score=1,
                supported_claims=1,
                total_claims=1,
                claims=[
                    ClaimVerification(
                        claim=claim,
                        chunk_id=hit.payload["chunk_id"],
                        category="direct_answer",
                        verdict="yes",
                    )
                ],
            ),
            "agent_trace": [],
            "role": "citizen",
        }
    )["final_answer"]


CRPC = "The Code of Criminal Procedure, 1973"


class TestAClaimAboutNow:
    """Published as verified in the recorded run, with 0 unsupported claims."""

    @pytest.mark.parametrize(
        "claim",
        [
            "The Code of Criminal Procedure, 1973 (CrPC) currently governs the law on arrest without a warrant in India",
            "The BNSS has not yet been fully implemented, so CrPC remains in force",
            "The CrPC still applies to every arrest",
        ],
    )
    def test_repealed_law_cannot_ground_it(self, claim: str) -> None:
        assert claim not in _generate(_hit("c", CRPC), claim)

    def test_repealed_law_can_still_say_what_the_law_was(self) -> None:
        claim = "Section 41 of the Code allowed arrest without a warrant for conduct before 1 July 2024"
        assert claim in _generate(_hit("c", CRPC), claim)

    def test_law_in_force_can_ground_it(self) -> None:
        claim = "The BNSS currently governs arrest without a warrant"
        hit = _hit("b", "The Bharatiya Nagarik Suraksha Sanhita, 2023", section="35")
        assert claim in _generate(hit, claim)


class TestACuratedFamilyDoesNotCoverItsRepealedMembers:
    def test_an_explicit_flag_beats_an_in_force_prefix(self) -> None:
        decision = resolve_currency(
            {
                "title": "The Juvenile Justice (Care and Protection of Children) Act, 2000 (superseded by the Act of 2015)",
                "is_superseded": True,
            }
        )
        assert decision.status is CurrencyStatus.SUPERSEDED

    def test_the_current_member_stays_in_force(self) -> None:
        decision = resolve_currency(
            {"title": "The Juvenile Justice (Care and Protection of Children) Act, 2015", "is_superseded": False}
        )
        assert decision.status is CurrencyStatus.IN_FORCE

    def test_a_curated_superseded_row_keeps_its_successor(self) -> None:
        decision = resolve_currency({"title": "The Indian Penal Code", "is_superseded": True})
        assert decision.superseded_by == "The Bharatiya Nyaya Sanhita, 2023"


@pytest.mark.parametrize("title", ["The Arms Rules, 1962.", "THE ARMS RULES, 1962"])
def test_the_arms_rules_of_1962_are_superseded_with_prior_conduct_saved(title: str) -> None:
    decision = resolve_currency({"title": title})
    assert decision.status is CurrencyStatus.SUPERSEDED
    assert decision.superseded_by == "The Arms Rules, 2016"
    assert decision.saves_prior_conduct is True


class TestConfidenceGrades:
    def _grade(self, *payloads: dict):
        by_id = {f"c{index}": payload for index, payload in enumerate(payloads)}
        return section_confidence("legal_basis", list(by_id), by_id, claim_count=len(by_id))

    def test_repealed_sources_are_never_strong(self) -> None:
        grade = self._grade(
            {"title": CRPC, "document_type": "bare_act", "canonical_document_id": "crpc"},
            {"title": "The Indian Penal Code", "document_type": "bare_act", "canonical_document_id": "ipc"},
        )
        assert grade.label is ConfidenceLabel.MODERATE
        assert "no longer in force" in grade.reason

    def test_two_chunks_of_one_act_are_one_source(self) -> None:
        act = {"title": "The Bharatiya Nyaya Sanhita, 2023", "document_type": "bare_act", "canonical_document_id": "bns"}
        grade = self._grade(dict(act), dict(act))
        assert grade.label is ConfidenceLabel.MODERATE
        assert grade.source_count == 1

    def test_two_acts_in_force_are_strong(self) -> None:
        grade = self._grade(
            {"title": "The Bharatiya Nyaya Sanhita, 2023", "document_type": "bare_act", "canonical_document_id": "bns"},
            {"title": "The Bharatiya Nagarik Suraksha Sanhita, 2023", "document_type": "bare_act", "canonical_document_id": "bnss"},
        )
        assert grade.label is ConfidenceLabel.STRONG


def test_one_old_section_names_every_section_it_moved_to() -> None:
    """A plain dict kept only the last, so CrPC s.154 read as BNSS s.173(3)."""
    claim = "A judgment explained how an FIR is registered"
    hit = _hit(
        "j",
        "State v. Someone",
        section="",
        source_type="judgment",
        document_type="judgment",
        cited_provisions=["crpc:154"],
    )
    answer = _generate(hit, claim)
    mappings = repeal_notice(hit.payload).mappings
    assert len({mapping.to_section for mapping in mappings}) > 1, "this test needs a one-to-many pair"
    for mapping in mappings:
        assert f"BNSS s.{mapping.to_section}" in answer
