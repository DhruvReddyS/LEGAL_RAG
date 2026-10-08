"""A verdict array that cannot come back short.

The verifier routinely returned fewer verdicts than claims -- measured runs
came back with three for ten and three for fourteen -- and that cost twice
over. Every missing claim triggered a second request, which is another prefill
of the same premises and another decode; and any claim still unadjudicated
after that was recorded as refuted, suppressing verified law the verifier had
never rejected.

`minItems == maxItems == claim_count` is compiled into the sampling grammar, so
the array cannot close early. These tests pin the schema, the clamp, the
positional contract, and the fallback that still exists for a host whose
grammar conversion ignores the bound.
"""

from __future__ import annotations

import pytest

from app.core.config import settings

from app.agents.verification_agent import (
    MAX_VERDICTS,
    VerdictItem,
    VerificationBatch,
    verdicts_for_exactly,
    verification_node,
)
from app.services.retrieval import RetrievalHit


def _hit(chunk_id: str, text: str = "The premise text that entails the claim.") -> RetrievalHit:
    return RetrievalHit(
        point_id=chunk_id,
        payload={"chunk_id": chunk_id, "text": text, "title": "Authority", "is_current": True},
        dense_score=0.9,
        sparse_score=0.1,
        fused_score=0.9,
        reranker_score=0.9,
    )


def _draft(claim_count: int) -> str:
    return "\n".join(
        f"[LEGAL_BASIS] Claim number {index} states a rule. [SRC:chunk-{index}]"
        for index in range(1, claim_count + 1)
    )


def _hits(claim_count: int) -> list[RetrievalHit]:
    return [_hit(f"chunk-{index}") for index in range(1, claim_count + 1)]


@pytest.fixture
def grammar_enabled(monkeypatch):
    """The grammar is off in production until it is measured in isolation.

    It cut model calls per query from 2.86 to 2.14 and unadjudicated claims
    to zero, but the same run showed published citations falling from 3.14
    per query to 2.43 on a host that decoded 58% faster, which cannot
    separate the two. These tests cover the behaviour the setting selects.
    """
    monkeypatch.setattr(settings, "verification_exact_verdict_grammar_enabled", True)


class RecordingLLM:
    """Returns a fixed number of verdicts, however many were asked for."""

    def __init__(self, *, verdicts_returned: int | None = None) -> None:
        self.verdicts_returned = verdicts_returned
        self.schemas: list[type] = []
        self.prompts: list[str] = []

    async def structured_with_metrics(self, prompt, schema, *, attempts=3, num_predict=1800):
        self.schemas.append(schema)
        self.prompts.append(prompt)
        requested = schema.model_json_schema()["properties"]["verdicts"].get("minItems")
        count = requested if self.verdicts_returned is None else self.verdicts_returned
        return schema.model_construct(
            verdicts=["yes"] * int(count or 0), claims=[]
        ), [{"operation": "structured", "attempt": 1}]


def test_the_schema_pins_the_array_to_exactly_the_claim_count() -> None:
    schema = verdicts_for_exactly(7)
    verdicts = schema.model_json_schema()["properties"]["verdicts"]
    assert verdicts["minItems"] == 7
    assert verdicts["maxItems"] == 7
    assert "verdicts" in schema.model_json_schema()["required"]


def test_the_schema_is_a_verification_batch_so_every_reader_still_works() -> None:
    """`collect()` and the stored fixtures both accept the base shape."""
    assert issubclass(verdicts_for_exactly(3), VerificationBatch)
    assert verdicts_for_exactly(3).model_validate(
        {"verdicts": ["yes", "no", "partial"]}
    ).verdicts == ["yes", "no", "partial"]


def test_the_claim_count_is_clamped_to_what_the_base_schema_allows() -> None:
    """A claim may cite three sources, so ten claims can make thirty pairs.

    The grammar cannot require more entries than the base field permits, and
    a zero-length requirement would describe an empty array as mandatory.
    """
    assert verdicts_for_exactly(0).model_json_schema()["properties"]["verdicts"]["minItems"] == 1
    assert (
        verdicts_for_exactly(MAX_VERDICTS + 50).model_json_schema()["properties"]["verdicts"]["maxItems"]
        == MAX_VERDICTS
    )


def test_schemas_are_cached_per_count() -> None:
    assert verdicts_for_exactly(5) is verdicts_for_exactly(5)
    assert verdicts_for_exactly(5) is not verdicts_for_exactly(6)


@pytest.mark.asyncio
async def test_a_complete_verdict_array_costs_exactly_one_request(grammar_enabled) -> None:
    """The second request existed only to collect what the first skipped."""
    llm = RecordingLLM()
    state = {"draft_answer": _draft(6), "retrieved_chunks": _hits(6), "stage_metrics": []}
    result = await verification_node(state, llm)  # type: ignore[arg-type]

    assert len(llm.schemas) == 1
    metric = result["stage_metrics"][-1]
    assert metric["outputs"]["second_verification_request_used"] is False
    assert metric["outputs"]["unadjudicated_claim_count"] == 0
    assert metric["outputs"]["verdict_schema_exact_length"] == 6
    assert result["verification_result"].supported_claims == 6


@pytest.mark.asyncio
async def test_the_prompt_states_the_count_as_well_as_the_grammar() -> None:
    """Belt and braces: a host that drops the bound still reads the number."""
    llm = RecordingLLM()
    state = {"draft_answer": _draft(4), "retrieved_chunks": _hits(4), "stage_metrics": []}
    await verification_node(state, llm)  # type: ignore[arg-type]
    assert "exactly 4 verdicts" in llm.prompts[0]


@pytest.mark.asyncio
async def test_a_host_that_ignores_the_bound_still_gets_the_second_request(grammar_enabled) -> None:
    """The fallback is kept, not replaced.

    The grammar is enforced by the inference host, and this code cannot
    verify that it was. If a short array arrives anyway, the behaviour must
    be the one that existed before: ask again for the claims that were
    skipped rather than record them as refuted.
    """
    llm = RecordingLLM(verdicts_returned=2)
    state = {"draft_answer": _draft(5), "retrieved_chunks": _hits(5), "stage_metrics": []}
    result = await verification_node(state, llm)  # type: ignore[arg-type]

    assert len(llm.schemas) == 2, "the skipped claims must be asked for again"
    assert result["stage_metrics"][-1]["outputs"]["second_verification_request_used"] is True
    # The second request is scoped to the outstanding claims only.
    assert llm.schemas[1].model_json_schema()["properties"]["verdicts"]["minItems"] == 3


@pytest.mark.asyncio
async def test_an_unadjudicated_claim_is_still_never_published() -> None:
    """Changing how verdicts are requested must not change what publishes.

    A claim with no verdict is unknown, not supported. It is recorded as
    "no" with an explicit reason and excluded from the support denominator,
    exactly as before.
    """
    llm = RecordingLLM(verdicts_returned=0)
    state = {"draft_answer": _draft(3), "retrieved_chunks": _hits(3), "stage_metrics": []}
    result = await verification_node(state, llm)  # type: ignore[arg-type]
    verification = result["verification_result"]
    assert verification.supported_claims == 0
    assert all(item.verdict == "no" for item in verification.claims)
    assert {item.reason for item in verification.claims} == {"No verifier result"}


def test_the_legacy_object_shape_is_still_accepted() -> None:
    """Stored fixtures and an older model shape must keep parsing."""
    batch = VerificationBatch(claims=[VerdictItem(index=1, verdict="partial", reason="thin")])
    assert batch.verdicts == []
    assert batch.claims[0].verdict == "partial"


def test_the_grammar_is_off_by_default() -> None:
    """Measured, effective, and not yet shown to be safe.

    It removed the second verification request in all nine runs that had
    needed one and drove unadjudicated claims to zero. It also coincided with
    published citations falling 23% and answers graded insufficient tripling,
    on a run whose host decoded 58% faster than the baseline -- so that run
    cannot attribute either effect. Verification is the one component where
    shipping an unmeasured change is a safety change, so the default is off
    until it has a run of its own.
    """
    assert settings.verification_exact_verdict_grammar_enabled is False


@pytest.mark.asyncio
async def test_with_the_setting_off_the_permissive_schema_is_requested() -> None:
    llm = RecordingLLM(verdicts_returned=0)
    state = {"draft_answer": _draft(4), "retrieved_chunks": _hits(4), "stage_metrics": []}
    await verification_node(state, llm)  # type: ignore[arg-type]
    assert llm.schemas[0] is VerificationBatch
    assert "minItems" not in VerificationBatch.model_json_schema()["properties"]["verdicts"]
