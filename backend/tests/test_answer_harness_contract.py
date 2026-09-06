"""The measurement must be able to read what the pipeline actually returns.

Every metric in answer_quality reads a key out of the workflow's final
state. If one of those keys is absent or holds a different shape than
expected, nothing raises: `state.get("verification_result")` returns None,
the published-claim count is zero, the unsupported-claim count is zero, and
a sixty-question run reports a clean sheet while measuring nothing.

That is the worst failure available to an evaluation harness, because its
output looks like success. So the contract is pinned here, against the real
LegalRAGWorkflow driven by fakes -- no index, no model, no GPU -- rather
than against a hand-built state dict, which would only prove the metrics
agree with my idea of the pipeline.
"""

from __future__ import annotations

import pytest

from app.agents.orchestrator import LegalRAGWorkflow
from app.agents.verification_agent import VerdictItem, VerificationBatch
from app.evaluation.answer_quality import assess_answer
from app.schemas.agents import ClaimVerification, VerificationResult
from tests.test_deep_pipeline_telemetry import (
    InstrumentedFakeLLM,
    InstrumentedFakeRetrieval,
)


class VerifyingFakeLLM(InstrumentedFakeLLM):
    """Returns a `yes` verdict, so the answering path is exercised.

    The telemetry fixture verifies nothing, which makes every run abstain --
    correct for what that test measures, and useless here: an abstention
    scores no ground coverage and no reading grade, so the metrics would be
    observed returning None rather than shown to work.
    """

    async def structured_with_metrics(self, prompt, schema, *, attempts=3):
        if schema is VerificationBatch:
            return VerificationBatch(
                claims=[VerdictItem(index=1, verdict="yes", reason="supported")]
            ), [{"operation": "structured", "attempt": 1, "prompt": {"characters": len(prompt)}}]
        return await super().structured_with_metrics(prompt, schema, attempts=attempts)


async def _finished_run(llm=None) -> dict:
    return await LegalRAGWorkflow(
        InstrumentedFakeRetrieval(),  # type: ignore[arg-type]
        llm or VerifyingFakeLLM(),  # type: ignore[arg-type]
    ).run(
        query="When must an FIR be registered?",
        role="citizen",
        case_id=None,
        history=[],
    )


@pytest.mark.asyncio
async def test_the_state_carries_every_key_the_metrics_read() -> None:
    state = await _finished_run()

    for key in ("final_answer", "retrieved_chunks", "citations", "verification_result"):
        assert key in state, (
            f"{key!r} is absent from the workflow result. answer_quality reads "
            "it with .get(), so its absence produces zeros rather than an "
            "error, and a whole evaluation run would report a clean sheet "
            "while measuring nothing."
        )


@pytest.mark.asyncio
async def test_the_shapes_are_what_the_metrics_expect() -> None:
    """Presence is not enough; the metrics index into these."""
    state = await _finished_run()

    assert isinstance(state["final_answer"], str)
    # unsupported_claims() reads .payload["chunk_id"] off each hit.
    for hit in state["retrieved_chunks"]:
        assert isinstance(hit.payload, dict)
        assert "chunk_id" in hit.payload
    # currency_assessment() reads .chunk_id off each citation.
    for citation in state["citations"]:
        assert isinstance(citation.chunk_id, str)
    # _published_claims() requires this exact type, not a dict or a list.
    assert isinstance(state["verification_result"], VerificationResult)


@pytest.mark.asyncio
async def test_a_real_run_scores_without_raising_and_without_silent_zeros() -> None:
    """The end-to-end shape of one measured question."""
    state = await _finished_run()

    quality = assess_answer(
        state,
        item_id="fir-registration",
        role="citizen",
        expectation="answer",
        grounds=[{"name": "registration is required", "any_of": ["registration", "required"]}],
    )

    # The standing rule, measured: this must be zero on every run.
    assert quality.unsupported_claim_count == 0
    # Ground coverage was computed rather than skipped. None here would mean
    # the answer was read as an abstention, which the fake is not.
    assert quality.ground_coverage is not None
    assert quality.reading_grade is not None


@pytest.mark.asyncio
async def test_an_unsupported_claim_would_actually_be_caught() -> None:
    """The rule's detector is exercised, not merely observed returning zero.

    Every other assertion here sees unsupported_claim_count == 0, which is
    also exactly what a broken detector returns. This puts a real violation
    into a real finished state and requires it to be found.
    """
    state = await _finished_run()
    result = state["verification_result"]
    assert result.claims, "fixture produced no verified claims to extend"

    state["verification_result"] = VerificationResult(
        score=result.score,
        supported_claims=result.supported_claims + 1,
        total_claims=result.total_claims + 1,
        claims=[
            *result.claims,
            ClaimVerification(
                claim="A claim citing evidence that was never retrieved.",
                chunk_id="chunk-never-retrieved",
                verdict="yes",
            ),
        ],
    )

    quality = assess_answer(state, item_id="x", role="citizen", expectation="answer")

    assert quality.unsupported_claim_count == 1
    assert "chunk-never-retrieved" in quality.unsupported_claim_details[0]
