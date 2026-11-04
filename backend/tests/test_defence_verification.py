"""A defence point is verified against law, not against the user's own account."""

from __future__ import annotations

import pytest

from app.agents.defence_strategy_agent import DefenceStrategyAgent
from app.agents.verification_agent import VerificationBatch
from app.schemas.strategy import DefenceAnalysisDraft, StrategyPoint
from app.services.retrieval import RetrievalHit


class _Retrieval:
    async def search_across_collections_with_timings(self, *args, **kwargs):
        hit = RetrievalHit(
            point_id="law",
            payload={"chunk_id": "law", "title": "BNSS", "text": "LAW TEXT HERE", "page_start": 1, "page_end": 1},
            dense_score=0.9,
            sparse_score=0.1,
            fused_score=0.9,
            reranker_score=0.9,
        )
        return [hit], {}


class _LLM:
    def __init__(self, batch: VerificationBatch) -> None:
        self.batch = batch
        self.verify_prompt = ""

    async def structured(self, prompt, schema, **kwargs):
        if issubclass(schema, VerificationBatch):
            self.verify_prompt = prompt
            return self.batch
        return DefenceAnalysisDraft(
            summary="A proposed analysis.",
            points=[
                StrategyPoint(
                    category="defence_point",
                    point="The arrest was unlawful.",
                    source_chunk_ids=["law"],
                ),
            ],
        )


async def _run(batch: VerificationBatch):
    llm = _LLM(batch)
    agent = DefenceStrategyAgent(_Retrieval(), llm)  # type: ignore[arg-type]
    result = await agent.run(case_id="case-1", case_scenario="USER ACCOUNT HERE", advocate_position=None)
    return result, llm


@pytest.mark.asyncio
async def test_the_users_account_is_labelled_as_facts_not_law() -> None:
    _, llm = await _run(VerificationBatch(verdicts=["yes"]))
    law_block = llm.verify_prompt.split("LAW:\n")[1].split("UNVERIFIED FACTS:")[0]
    assert "LAW TEXT HERE" in law_block
    assert "USER ACCOUNT HERE" not in law_block


@pytest.mark.asyncio
async def test_the_compact_verdict_form_is_read() -> None:
    result, _ = await _run(VerificationBatch(verdicts=["yes"]))
    assert len(result.points) == 1


@pytest.mark.asyncio
async def test_a_wrong_verdict_count_publishes_nothing() -> None:
    result, _ = await _run(VerificationBatch(verdicts=["yes", "yes"]))
    assert result.points == []


@pytest.mark.asyncio
async def test_the_search_follows_the_case_rather_than_one_offence() -> None:
    seen: list[str] = []

    class _Recording(_Retrieval):
        async def search_across_collections_with_timings(self, query, **kwargs):
            seen.append(query)
            return await super().search_across_collections_with_timings(query, **kwargs)

    agent = DefenceStrategyAgent(_Recording(), _LLM(VerificationBatch(verdicts=["yes"])))  # type: ignore[arg-type]
    await agent.run(case_id="case-1", case_scenario="A cheating complaint", advocate_position=None)
    assert seen[0].startswith("A cheating complaint")
    assert "NDPS" not in seen[0]
    assert "contraband" not in seen[0]
