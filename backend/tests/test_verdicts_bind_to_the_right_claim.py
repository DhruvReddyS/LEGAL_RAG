"""A verdict must land on the claim it was given for.

Claims were numbered in draft order but displayed grouped by source, so a draft
citing chunks A, B, A showed claims 1, 3, 2. Verdicts are positional, and were
bound as 1, 2, 3: a "yes" for claim 3 published claim 2, which the verifier had
rejected. Only published claims reach the reader, so this is the one mistake in
the pipeline that turns a refusal into a published statement.

The earlier tests could not see it. Their fake verifiers returned a fixed list
and shared the code's assumption about order. The fake here reads the prompt and
answers in the order the claims appear, as a model does.
"""

from __future__ import annotations

import re

import pytest

from app.agents.verification_agent import VerificationBatch, verification_node
from app.services.retrieval import RetrievalHit

SUPPORTED = "SUPPORTED"
REJECTED = "REJECTED"


def _hit(chunk_id: str) -> RetrievalHit:
    return RetrievalHit(
        point_id=chunk_id,
        payload={"chunk_id": chunk_id, "text": "Premise text.", "title": "Authority"},
        dense_score=0.9,
        sparse_score=0.1,
        fused_score=0.9,
        reranker_score=0.9,
    )


def _state(*claims: tuple[str, str]) -> dict:
    chunk_ids = list(dict.fromkeys(chunk_id for _, chunk_id in claims))
    return {
        "draft_answer": "\n".join(f"[LEGAL_BASIS] {text}. [SRC:{chunk_id}]" for text, chunk_id in claims),
        "retrieved_chunks": [_hit(chunk_id) for chunk_id in chunk_ids],
        "stage_metrics": [],
        "agent_trace": [],
    }


class ReadsThePrompt:
    """Judges each claim by its text, answering in the order claims are shown."""

    def __init__(self, *, keep_first_call: int | None = None, extra_verdicts: int = 0) -> None:
        self.keep_first_call = keep_first_call
        self.extra_verdicts = extra_verdicts
        self.calls = 0
        self.prompts: list[str] = []

    async def structured_with_metrics(self, prompt, schema, **kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        shown = re.findall(r"^CLAIM \d+: (.*)$", prompt, flags=re.MULTILINE)
        verdicts = ["yes" if SUPPORTED in text else "no" for text in shown]
        if self.calls == 1 and self.keep_first_call is not None:
            verdicts = verdicts[: self.keep_first_call]
        if self.calls == 1:
            verdicts = verdicts + ["yes"] * self.extra_verdicts
        return VerificationBatch(verdicts=verdicts), []


class AlwaysShort:
    """A host that ignores the bound on every request."""

    def __init__(self) -> None:
        self.calls = 0

    async def structured_with_metrics(self, prompt, schema, **kwargs):
        self.calls += 1
        return VerificationBatch(verdicts=["yes"]), []


# Sources alternate, so display order differs from draft order.
INTERLEAVED = (
    (f"First {REJECTED} proposition", "chunk-a"),
    (f"Second {REJECTED} proposition", "chunk-b"),
    (f"Third {SUPPORTED} proposition", "chunk-a"),
    (f"Fourth {SUPPORTED} proposition", "chunk-b"),
)


def _verdicts(result: dict) -> dict[str, str]:
    return {item.claim: item.verdict for item in result["verification_result"].claims}


def _assert_every_verdict_matches_its_text(result: dict) -> None:
    verdicts = _verdicts(result)
    assert len(verdicts) == len(INTERLEAVED)
    for claim, verdict in verdicts.items():
        assert verdict == ("yes" if SUPPORTED in claim else "no"), claim


@pytest.mark.asyncio
async def test_positional_verdicts_follow_the_claims_as_displayed() -> None:
    result = await verification_node(_state(*INTERLEAVED), ReadsThePrompt())  # type: ignore[arg-type]
    _assert_every_verdict_matches_its_text(result)


@pytest.mark.asyncio
async def test_claims_are_numbered_in_the_order_they_are_shown() -> None:
    llm = ReadsThePrompt()
    await verification_node(_state(*INTERLEAVED), llm)  # type: ignore[arg-type]
    numbers = [int(number) for number in re.findall(r"^CLAIM (\d+):", llm.prompts[0], flags=re.MULTILINE)]
    assert numbers == sorted(numbers)


@pytest.mark.asyncio
async def test_a_short_array_is_never_guessed_at() -> None:
    """Which verdicts a short array skipped cannot be known, so none are used."""
    llm = ReadsThePrompt(keep_first_call=1)
    result = await verification_node(_state(*INTERLEAVED), llm)  # type: ignore[arg-type]

    assert llm.calls == 2
    assert len(re.findall(r"^CLAIM \d+:", llm.prompts[1], flags=re.MULTILINE)) == len(INTERLEAVED)
    _assert_every_verdict_matches_its_text(result)
    assert result["stage_metrics"][-1]["outputs"]["mismatched_verdict_arrays"] == 1


@pytest.mark.asyncio
async def test_a_long_array_is_never_guessed_at_either() -> None:
    llm = ReadsThePrompt(extra_verdicts=2)
    result = await verification_node(_state(*INTERLEAVED), llm)  # type: ignore[arg-type]

    assert llm.calls == 2
    _assert_every_verdict_matches_its_text(result)


@pytest.mark.asyncio
async def test_the_second_request_demands_the_exact_count_by_default() -> None:
    """Off for the first pass until measured; here a wrong count is already known."""
    seen: list[type] = []

    class _Records(ReadsThePrompt):
        async def structured_with_metrics(self, prompt, schema, **kwargs):
            seen.append(schema)
            return await super().structured_with_metrics(prompt, schema, **kwargs)

    await verification_node(_state(*INTERLEAVED), _Records(keep_first_call=1))  # type: ignore[arg-type]
    assert seen[1].model_json_schema()["properties"]["verdicts"]["minItems"] == len(INTERLEAVED)


@pytest.mark.asyncio
async def test_nothing_publishes_when_the_count_never_matches() -> None:
    """Failing closed: an answer lost is better than a claim published by guess."""
    llm = AlwaysShort()
    result = await verification_node(_state(*INTERLEAVED), llm)  # type: ignore[arg-type]

    assert llm.calls == 2
    verification = result["verification_result"]
    assert verification.supported_claims == 0
    assert {item.reason for item in verification.claims} == {"No verifier result"}


@pytest.mark.asyncio
async def test_indexed_verdicts_still_bind_by_index() -> None:
    class _Indexed:
        async def structured_with_metrics(self, prompt, schema, **kwargs):
            shown = re.findall(r"^CLAIM (\d+): (.*)$", prompt, flags=re.MULTILINE)
            return VerificationBatch(
                claims=[
                    {"index": int(number), "verdict": "yes" if SUPPORTED in text else "no"}
                    for number, text in reversed(shown)
                ]
            ), []

    result = await verification_node(_state(*INTERLEAVED), _Indexed())  # type: ignore[arg-type]
    _assert_every_verdict_matches_its_text(result)


@pytest.mark.asyncio
async def test_claims_come_back_in_draft_order() -> None:
    """Grouping is for the verifier. The answer must still read as drafted."""
    result = await verification_node(_state(*INTERLEAVED), ReadsThePrompt())  # type: ignore[arg-type]
    returned = [item.claim for item in result["verification_result"].claims]
    assert returned == [text for text, _ in INTERLEAVED]


@pytest.mark.asyncio
async def test_the_verifier_is_told_which_law_each_premise_is() -> None:
    """A section's text does not name its Act, so a claim naming it could never pass."""
    state = _state(("Section 35 of the BNSS allows arrest", "chunk-a"))
    hit = state["retrieved_chunks"][0]
    hit.payload.update(act_name="Bharatiya Nagarik Suraksha Sanhita, 2023", section="35")
    llm = ReadsThePrompt()
    await verification_node(state, llm)  # type: ignore[arg-type]
    assert "THIS PREMISE IS: Bharatiya Nagarik Suraksha Sanhita, 2023, section 35" in llm.prompts[0]
    assert "what" in llm.prompts[0] and "must rest on the premise text" in llm.prompts[0]


@pytest.mark.asyncio
async def test_a_premise_with_no_recorded_law_says_nothing_about_it() -> None:
    state = _state(("A claim", "chunk-a"))
    state["retrieved_chunks"][0].payload.update(act_name="", title="")
    llm = ReadsThePrompt()
    await verification_node(state, llm)  # type: ignore[arg-type]
    assert "THIS PREMISE IS" not in llm.prompts[0]
