from __future__ import annotations

from app.agents.orchestrator import LegalRAGWorkflow
from app.agents.response_generation import response_generation_node
from app.agents.verification_agent import _claim_marker_pairs
from app.schemas.agents import ClaimVerification, VerificationResult
from app.services.retrieval import RetrievalHit


def _hit(chunk_id: str = "chunk-1") -> RetrievalHit:
    return RetrievalHit(
        point_id="point-1",
        payload={
            "chunk_id": chunk_id,
            "title": "Test Act",
            "source_type": "act",
            "page_start": 2,
            "page_end": 3,
            "act_name": "Test Act",
            "section": "1",
            "text": "The supported proposition.",
        },
        dense_score=0.5,
        sparse_score=None,
        fused_score=0.03,
        reranker_score=0.9,
    )


def test_response_generation_maps_only_retrieved_markers() -> None:
    result = response_generation_node(
        {
            "draft_answer": "The proposition applies. [SRC:chunk-1]",
            "retrieved_chunks": [_hit()],
            "verification_result": VerificationResult(
                score=1,
                supported_claims=1,
                total_claims=1,
                claims=[
                    ClaimVerification(
                        claim="The proposition applies.",
                        chunk_id="chunk-1",
                        verdict="yes",
                    )
                ],
            ),
            "agent_trace": [],
        }
    )
    assert result["final_answer"] == "The proposition applies [Source 1]."
    assert result["citations"][0].chunk_id == "chunk-1"
    assert result["evidence_strength"] == "strong"


def test_response_generation_refuses_low_confidence_draft() -> None:
    result = response_generation_node(
        {
            "draft_answer": "Unsupported answer [SRC:chunk-1]",
            "retrieved_chunks": [_hit()],
            "verification_result": VerificationResult(score=0.49),
            "agent_trace": [],
        }
    )
    assert result["evidence_strength"] == "insufficient"
    assert result["citations"] == []
    assert "could not find enough reliable support" in result["final_answer"]


def test_response_generation_does_not_publish_partially_supported_compound_claim() -> None:
    result = response_generation_node(
        {
            "draft_answer": "One supported fact plus one invented instruction [SRC:chunk-1]",
            "retrieved_chunks": [_hit()],
            "verification_result": VerificationResult(
                score=0.5,
                supported_claims=0,
                total_claims=1,
                claims=[
                    ClaimVerification(
                        claim="One supported fact plus one invented instruction",
                        chunk_id="chunk-1",
                        verdict="partial",
                    )
                ],
            ),
            "agent_trace": [],
        }
    )
    assert result["evidence_strength"] == "insufficient"
    assert result["confidence_score"] == 0
    assert result["citations"] == []
    assert "could not find enough reliable support" in result["final_answer"]


def test_orchestrator_retry_is_bounded_at_two() -> None:
    assert LegalRAGWorkflow._route_after_verification(
        {"verification_result": VerificationResult(score=0.1), "retry_count": 0}
    ) == "retry"
    assert LegalRAGWorkflow._route_after_verification(
        {"verification_result": VerificationResult(score=0.1), "retry_count": 2}
    ) == "proceed"


def test_orchestrator_retry_counter_increments() -> None:
    assert LegalRAGWorkflow._retry({"retry_count": 1}) == {"retry_count": 2}


def test_claim_parser_preserves_legal_abbreviations() -> None:
    answer = (
        "Registration is mandatory for a cognizable offence [SRC:one]. "
        "The Supreme Court reiterated this in State of U.P. v. A. [SRC:two]."
    )
    assert _claim_marker_pairs(answer) == [
        ("Registration is mandatory for a cognizable offence", "one"),
        ("The Supreme Court reiterated this in State of U.P. v. A", "two"),
    ]


def test_role_context_selects_auditable_role_specific_agent() -> None:
    result = LegalRAGWorkflow._role_context(
        {"role": "police", "case_id": "case-1", "query": "Check electronic evidence authenticity", "agent_trace": []}
    )
    event = result["agent_trace"][0]
    assert event.node == "role_context"
    assert event.details["agent_label"] == "Police investigation and procedure assistant"
    assert event.details["specialist_agent_label"] == "Evidence Integrity Agent"
    assert result["specialist_agent_id"] == "evidence_integrity"
    assert event.details["case_scoped"] is True
