from __future__ import annotations

from app.agents.orchestrator import LegalRAGWorkflow
from app.agents.query_understanding import query_understanding_node
from app.agents.reasoning_agent import MAX_EVIDENCE_TEXT_CHARACTERS, format_evidence
from app.agents.retrieval_agent import retrieval_node
from app.agents.response_generation import response_generation_node
from app.agents.verification_agent import _claim_marker_pairs, _format_verification_items
from app.schemas.agents import ClaimVerification, QueryIntent, VerificationResult
from app.services.retrieval import RetrievalHit, RetrievalTimings
import pytest


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


def test_reasoning_evidence_caps_chunk_text_without_dropping_metadata() -> None:
    hit = _hit()
    hit.payload["text"] = "x" * (MAX_EVIDENCE_TEXT_CHARACTERS + 25)

    evidence = format_evidence([hit])

    assert f"CHUNK_ID: {hit.payload['chunk_id']}" in evidence
    assert "x" * MAX_EVIDENCE_TEXT_CHARACTERS in evidence
    assert "x" * (MAX_EVIDENCE_TEXT_CHARACTERS + 1) not in evidence


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
    assert result["final_answer"].startswith(
        "## Why this is the legal position\n\n- The proposition applies [Source 1]."
    )
    assert "Legal decision-support information" in result["final_answer"]
    assert "## Source currency" in result["final_answer"]
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
    result = LegalRAGWorkflow._retry(
        {
            "retry_count": 1,
            "verification_result": VerificationResult(score=0.1),
            "stage_metrics": [],
        }
    )
    assert result["retry_count"] == 2
    assert result["stage_metrics"][0]["stage"] == "retry"
    assert result["stage_metrics"][0]["retry_index"] == 2


def test_claim_parser_preserves_legal_abbreviations() -> None:
    answer = (
        "Registration is mandatory for a cognizable offence [SRC:one]. "
        "The Supreme Court reiterated this in State of U.P. v. A. [SRC:two]."
    )
    assert _claim_marker_pairs(answer) == [
        ("Registration is mandatory for a cognizable offence", "one"),
        ("The Supreme Court reiterated this in State of U.P. v. A", "two"),
    ]


def test_verification_items_include_shared_premise_text_once() -> None:
    text = "The shared authoritative premise."
    items = _format_verification_items(
        [
            ("direct_answer", "First claim", "chunk-1"),
            ("next_step", "Second claim", "chunk-1"),
        ],
        {"chunk-1": text},
    )

    assert items.count(text) == 1
    assert items.count("CHUNK_ID: chunk-1") == 1
    assert items.count("SOURCE_REF: SOURCE_1") == 2
    assert "CLAIM 1: First claim" in items
    assert "CLAIM 2: Second claim" in items


def test_response_generation_preserves_verified_assistant_structure() -> None:
    result = response_generation_node(
        {
            "draft_answer": "unused",
            "retrieved_chunks": [_hit()],
            "verification_result": VerificationResult(
                score=1,
                supported_claims=2,
                total_claims=2,
                claims=[
                    ClaimVerification(
                        claim="You may submit the information in the supported manner",
                        chunk_id="chunk-1",
                        category="direct_answer",
                        verdict="yes",
                    ),
                    ClaimVerification(
                        claim="Keep the supporting record described by the authority",
                        chunk_id="chunk-1",
                        category="next_step",
                        verdict="yes",
                    ),
                ],
            ),
            "agent_trace": [],
        }
    )
    answer = result["final_answer"]
    assert answer.index("## Direct answer") < answer.index("## What you can do now")
    assert "1. Keep the supporting record" in answer
    assert "[Source 1]" in answer
    assert "RAG" not in answer


def test_response_generation_never_publishes_superseded_authority() -> None:
    hit = _hit()
    hit.payload["is_superseded"] = True
    result = response_generation_node(
        {
            "role": "citizen",
            "retrieved_chunks": [hit],
            "verification_result": VerificationResult(
                score=1,
                supported_claims=1,
                total_claims=1,
                claims=[
                    ClaimVerification(
                        claim="A historical rule applies",
                        chunk_id="chunk-1",
                        category="direct_answer",
                        verdict="yes",
                    )
                ],
            ),
            "agent_trace": [],
        }
    )
    assert result["citations"] == []
    assert "could not find enough reliable support" in result["final_answer"]


def test_citation_status_keeps_strongest_verdict_for_shared_chunk() -> None:
    result = response_generation_node(
        {
            "role": "citizen",
            "retrieved_chunks": [_hit()],
            "verification_result": VerificationResult(
                score=0.5,
                supported_claims=1,
                total_claims=2,
                claims=[
                    ClaimVerification(
                        claim="The supported filing step",
                        chunk_id="chunk-1",
                        category="next_step",
                        verdict="yes",
                    ),
                    ClaimVerification(
                        claim="An unsupported extra detail",
                        chunk_id="chunk-1",
                        category="limit",
                        verdict="no",
                    ),
                ],
            ),
            "agent_trace": [],
        }
    )

    assert result["citations"][0].verification_status == "verified"


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


class _IntentLLM:
    async def structured_with_metrics(self, prompt, schema, *, attempts=3):
        return QueryIntent(
            intent="Procedural guidance",
            entities=[],
            retrieval_query="how to file a pocos case",
        ), []


@pytest.mark.asyncio
async def test_query_understanding_normalizes_typo_and_preserves_corrected_entity() -> None:
    result = await query_understanding_node(
        {"query": "how to file a pocos case?", "history": [], "agent_trace": []},
        _IntentLLM(),  # type: ignore[arg-type]
    )

    assert result["retrieval_query"] == "how to file a POCSO case"
    assert result["intent"].entities == ["POCSO"]
    assert result["agent_trace"][-1].details["legal_term_corrections"]


class _CapturingRetrieval:
    def __init__(self) -> None:
        self.query = ""
        # Every pass, so a test can distinguish the query the node built from
        # the fallback re-query it may append afterwards.
        self.queries: list[str] = []

    async def search_across_collections_with_timings(self, query, **kwargs):
        self.query = query
        self.queries.append(query)
        return [], RetrievalTimings(
            embedding_ms=0.0,
            qdrant_ms=0.0,
            reranking_ms=0.0,
            total_ms=0.0,
        )


@pytest.mark.asyncio
async def test_retry_retrieval_keeps_normalized_query_instead_of_raw_typo() -> None:
    retrieval = _CapturingRetrieval()
    await retrieval_node(
        {
            "query": "how to file a pocos case?",
            "retrieval_query": "how to file a POCSO case",
            "intent": QueryIntent(entities=["POCSO"], retrieval_query="how to file a POCSO case"),
            "retry_count": 1,
            "role": "citizen",
            "case_id": None,
            "agent_trace": [],
        },
        retrieval,  # type: ignore[arg-type]
    )

    assert "POCSO" in retrieval.query
    assert "pocos" not in retrieval.query.casefold()


class _LowScoreRetrieval:
    def __init__(self) -> None:
        self.calls = []

    async def search_across_collections_with_timings(self, query, **kwargs):
        self.calls.append((query, kwargs["candidate_limit"], kwargs["result_limit"]))
        if len(self.calls) == 1:
            hits = [_hit("chunk-1")]
            hits[0].reranker_score = 0.05
        else:
            hits = [_hit(f"chunk-{index}") for index in range(2, 10)]
            for index, hit in enumerate(hits, 2):
                hit.point_id = f"point-{index}"
                hit.reranker_score = 0.74 - index / 100
            hits[-1].payload["title"] = "SOP for Registration of FIR"
        return hits, RetrievalTimings(
            embedding_ms=1.0,
            qdrant_ms=2.0,
            reranking_ms=3.0,
            total_ms=6.0,
            candidate_count=kwargs["candidate_limit"],
        )


class _HighScoreRetrieval(_LowScoreRetrieval):
    def __init__(self, *, top_text: str) -> None:
        super().__init__()
        self.top_text = top_text

    async def search_across_collections_with_timings(self, query, **kwargs):
        if not self.calls:
            self.calls.append((query, kwargs["candidate_limit"], kwargs["result_limit"]))
            hit = _hit("chunk-1")
            hit.payload["text"] = self.top_text
            hit.reranker_score = 0.90
            return [hit], RetrievalTimings(
                embedding_ms=1.0,
                qdrant_ms=2.0,
                reranking_ms=3.0,
                total_ms=6.0,
                candidate_count=kwargs["candidate_limit"],
            )
        return await super().search_across_collections_with_timings(query, **kwargs)


@pytest.mark.asyncio
async def test_initial_low_score_retrieval_uses_bounded_generalized_fallback() -> None:
    retrieval = _LowScoreRetrieval()
    result = await retrieval_node(
        {
            "query": "my dog is missing what should i do",
            "retrieval_query": "missing dog complaint",
            "intent": QueryIntent(retrieval_query="missing dog complaint"),
            "retry_count": 0,
            "role": "citizen",
            "case_id": None,
            "agent_trace": [],
        },
        retrieval,  # type: ignore[arg-type]
    )

    assert retrieval.calls[0] == ("missing dog complaint", 20, 5)
    assert retrieval.calls[1][1:] == (40, 8)
    assert "General Diary entry" in retrieval.calls[1][0]
    assert [hit.payload["chunk_id"] for hit in result["retrieved_chunks"]][:3] == [
        "chunk-1",
        "chunk-2",
        "chunk-9",
    ]
    assert len(result["retrieved_chunks"]) == 8
    assert result["agent_trace"][-1].details["final_max_reranker_score"] == pytest.approx(0.72)
    assert result["agent_trace"][-1].details["low_score_fallback_triggered"] is True


@pytest.mark.asyncio
async def test_high_score_without_topical_anchor_still_uses_fallback() -> None:
    retrieval = _HighScoreRetrieval(
        top_text="A constitutional privacy discussion about searches and warrants."
    )
    result = await retrieval_node(
        {
            "query": "my phone was snatched on the street",
            "retrieval_query": "phone stolen on the street complaint procedure",
            "intent": QueryIntent(
                retrieval_query="phone stolen on the street complaint procedure"
            ),
            "retry_count": 0,
            "role": "citizen",
            "case_id": None,
            "agent_trace": [],
        },
        retrieval,  # type: ignore[arg-type]
    )

    details = result["agent_trace"][-1].details
    assert len(retrieval.calls) == 2
    assert details["initial_max_reranker_score"] == pytest.approx(0.90)
    assert details["top_topic_anchor_matched"] is False
    assert details["fallback_trigger_reasons"] == ["missing_top_topic_anchor"]
    assert details["anchor_bypass_triggered"] is True
    assert retrieval.calls[1][0].count(
        "phone stolen on the street complaint procedure"
    ) == 2


@pytest.mark.asyncio
async def test_high_score_with_topical_anchor_suppresses_fallback() -> None:
    retrieval = _HighScoreRetrieval(
        top_text="A stolen phone on the street may be reported through the complaint procedure."
    )
    result = await retrieval_node(
        {
            "query": "my phone was snatched on the street",
            "retrieval_query": "phone stolen on the street complaint procedure",
            "intent": QueryIntent(
                retrieval_query="phone stolen on the street complaint procedure"
            ),
            "retry_count": 0,
            "role": "citizen",
            "case_id": None,
            "agent_trace": [],
        },
        retrieval,  # type: ignore[arg-type]
    )

    details = result["agent_trace"][-1].details
    assert len(retrieval.calls) == 1
    assert details["top_topic_anchor_matched"] is True
    assert details["fallback_trigger_reasons"] == []


@pytest.mark.asyncio
async def test_topic_anchor_matches_common_inflection_without_fallback() -> None:
    retrieval = _HighScoreRetrieval(
        top_text="Supreme Court guidelines for compounding cheque bounce cases."
    )
    result = await retrieval_node(
        {
            "query": "cheque bounced what is the procedure",
            "retrieval_query": "procedure for handling a bounced cheque",
            "intent": QueryIntent(
                retrieval_query="procedure for handling a bounced cheque"
            ),
            "retry_count": 0,
            "role": "citizen",
            "case_id": None,
            "agent_trace": [],
        },
        retrieval,  # type: ignore[arg-type]
    )

    assert len(retrieval.calls) == 1
    assert result["agent_trace"][-1].details["top_topic_anchor_matched"] is True


class _AnchoredProcedureFallbackRetrieval:
    def __init__(self) -> None:
        self.calls = []

    async def search_across_collections_with_timings(self, query, **kwargs):
        self.calls.append((query, kwargs["candidate_limit"], kwargs["result_limit"]))
        if len(self.calls) == 1:
            hit = _hit("irrelevant-high")
            hit.payload["text"] = "An age of consent discussion mentioning child marriage."
            hit.reranker_score = 0.90
            return [hit], RetrievalTimings(1.0, 2.0, 3.0, 6.0)
        hits = []
        for chunk_id, text, score in (
            ("generic-fir", "General FIR registration procedure.", 0.80),
            ("generic-old", "Old general criminal procedure commentary.", 0.70),
            ("generic-other", "Another general procedural authority.", 0.60),
            (
                "child-injunction",
                "A complaint about child marriage may be made to a Magistrate for an injunction.",
                0.50,
            ),
        ):
            hit = _hit(chunk_id)
            hit.point_id = chunk_id
            hit.payload["text"] = text
            hit.reranker_score = score
            hits.append(hit)
        return hits, RetrievalTimings(1.0, 2.0, 3.0, 6.0)


@pytest.mark.asyncio
async def test_anchor_bypass_prioritizes_topic_specific_procedure_from_fallback() -> None:
    retrieval = _AnchoredProcedureFallbackRetrieval()
    result = await retrieval_node(
        {
            "query": "child marriage is happening in my neighbourhood what should i do",
            "retrieval_query": "child marriage is happening in my neighbourhood what should i do",
            "intent": QueryIntent(
                retrieval_query="child marriage is happening in my neighbourhood what should i do"
            ),
            "retry_count": 0,
            "role": "citizen",
            "case_id": None,
            "agent_trace": [],
        },
        retrieval,  # type: ignore[arg-type]
    )

    assert [hit.payload["chunk_id"] for hit in result["retrieved_chunks"]][:3] == [
        "irrelevant-high",
        "generic-fir",
        "child-injunction",
    ]


@pytest.mark.asyncio
async def test_retry_pass_still_enforces_the_topic_anchor_gate() -> None:
    """The retry pass previously had no relevance floor at all.

    Restricting the gate to retry_count == 0 left the pass most likely to
    drift unguarded: it searches a broadened query after verification has
    already rejected the first answer.
    """
    retrieval = _LowScoreRetrieval()

    result = await retrieval_node(
        {
            "query": "my dog went missing, how do I report it",
            "retrieval_query": "missing pet report procedure",
            "intent": QueryIntent(
                entities=[], retrieval_query="missing pet report procedure"
            ),
            "retry_count": 1,
            "role": "citizen",
            "case_id": None,
            "agent_trace": [],
        },
        retrieval,  # type: ignore[arg-type]
    )

    details = result["agent_trace"][-1].details
    assert details["retry"] == 1
    assert details["low_score_fallback_triggered"] is True
    assert len(retrieval.calls) == 2, "the retry pass must be able to re-query"


@pytest.mark.asyncio
async def test_retry_query_is_built_from_the_topic_not_a_prior_expansion() -> None:
    """Retrieval writes its expansions back into state["retrieval_query"].

    Deriving the retry query from that compounded fallback scaffolding across
    passes, so each retry drifted further from what the user asked.
    """
    retrieval = _CapturingRetrieval()

    await retrieval_node(
        {
            "query": "is FIR registration mandatory for cognizable offences",
            # A first pass already appended fallback scaffolding here.
            "retrieval_query": (
                "is FIR registration mandatory for cognizable offences "
                "non-cognizable offence General Diary entry SOP complaint procedure"
            ),
            "intent": QueryIntent(
                entities=["FIR"],
                retrieval_query="is FIR registration mandatory for cognizable offences",
            ),
            "retry_count": 1,
            "role": "citizen",
            "case_id": None,
            "agent_trace": [],
        },
        retrieval,  # type: ignore[arg-type]
    )

    first_pass = retrieval.queries[0]
    assert "General Diary entry SOP" not in first_pass
    assert "is FIR registration mandatory for cognizable offences" in first_pass
    assert "governing law authoritative provision" in first_pass


@pytest.mark.asyncio
async def test_anchor_coverage_ignores_retry_scaffolding_terms() -> None:
    """Anchor coverage is judged against the topic, not the expanded query.

    "governing law authoritative provision" is search scaffolding. Counting it
    as topic vocabulary made the coverage threshold unreachable on any retry,
    which would have fired the fallback unconditionally.
    """
    retrieval = _HighScoreRetrieval(
        top_text=(
            "Registration of a first information report is mandatory where the "
            "information discloses a cognizable offence."
        )
    )

    result = await retrieval_node(
        {
            "query": "is FIR registration mandatory for cognizable offences",
            "retrieval_query": "is FIR registration mandatory for cognizable offences",
            "intent": QueryIntent(
                entities=["FIR"],
                retrieval_query="is FIR registration mandatory for cognizable offences",
            ),
            "retry_count": 1,
            "role": "citizen",
            "case_id": None,
            "agent_trace": [],
        },
        retrieval,  # type: ignore[arg-type]
    )

    details = result["agent_trace"][-1].details
    assert details["topic_query"] == "is FIR registration mandatory for cognizable offences"
    assert details["top_topic_anchor_matched"] is True
    assert details["low_score_fallback_triggered"] is False


@pytest.mark.asyncio
async def test_verification_caps_premise_text_per_source() -> None:
    """Reasoning capped its evidence; verification did not.

    The uncapped premise block reached ~12,900 tokens, which is 79% of the
    context window and 40-50 seconds of prefill before the first output token.
    """
    from app.agents.verification_agent import MAX_PREMISE_CHARACTERS, verification_node

    long_authority = "The officer shall record the information in writing. " * 400
    assert len(long_authority) > MAX_PREMISE_CHARACTERS * 3

    hit = _hit("chunk-1")
    hit.payload["text"] = long_authority

    captured: dict[str, str] = {}

    class _Verifier:
        async def structured_with_metrics(self, prompt, schema, **kwargs):
            captured["prompt"] = prompt
            return schema(claims=[{"index": 1, "verdict": "yes", "reason": "ok"}]), []

    result = await verification_node(
        {
            "draft_answer": "[DIRECT_ANSWER] Registration is mandatory. [SRC:chunk-1]",
            "retrieved_chunks": [hit],
            "agent_trace": [],
        },
        _Verifier(),  # type: ignore[arg-type]
    )

    assert len(captured["prompt"]) < MAX_PREMISE_CHARACTERS + 2000
    assert long_authority not in captured["prompt"]
    # Truncation must not cost the claim its verdict.
    assert result["verification_result"].score == 1.0
    assert result["verification_result"].claims[0].verdict == "yes"


@pytest.mark.asyncio
async def test_verification_premise_cap_keeps_every_distinct_source() -> None:
    """Capping is per source, so a long chunk cannot crowd out a short one."""
    from app.agents.verification_agent import verification_node

    first = _hit("chunk-1")
    first.payload["text"] = "Section 154 requires registration. " * 300
    second = _hit("chunk-2")
    second.payload["text"] = "A refusal may be escalated to the Superintendent."

    captured: dict[str, str] = {}

    class _Verifier:
        async def structured_with_metrics(self, prompt, schema, **kwargs):
            captured["prompt"] = prompt
            return schema(claims=[]), []

    await verification_node(
        {
            "draft_answer": (
                "[LEGAL_BASIS] Registration is required. [SRC:chunk-1] "
                "[NEXT_STEP] Escalate a refusal. [SRC:chunk-2]"
            ),
            "retrieved_chunks": [first, second],
            "agent_trace": [],
        },
        _Verifier(),  # type: ignore[arg-type]
    )

    assert "CHUNK_ID: chunk-1" in captured["prompt"]
    assert "CHUNK_ID: chunk-2" in captured["prompt"]
    assert "escalated to the Superintendent" in captured["prompt"]
