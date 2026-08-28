from __future__ import annotations

import pytest

from app.agents.retrieval_agent import retrieval_node
from app.agents.role_profiles import get_role_profile, profile_prompt, select_specialist_agent
from app.ingestion.init_qdrant import ADVOCATE_CASE_DATA, GLOBAL_LEGAL_CORPUS, POLICE_CASE_DATA
from app.schemas.agents import QueryIntent
from app.services.retrieval import RetrievalTimings


class CapturingRetrieval:
    def __init__(self) -> None:
        self.targets = []

    async def search_across_collections_with_timings(self, query: str, **kwargs):
        self.targets = kwargs["targets"]
        return [], RetrievalTimings(1, 2, 3, 6)


def state(role: str, case_id: str | None) -> dict:
    return {
        "query": "What authority applies?",
        "retrieval_query": "authority",
        "role": role,
        "case_id": case_id,
        "retry_count": 0,
        "intent": QueryIntent(retrieval_query="authority"),
        "agent_trace": [],
        "timings": {},
    }


def test_every_supported_role_has_distinct_agent_contract() -> None:
    citizen = get_role_profile("citizen")
    police = get_role_profile("police")
    advocate = get_role_profile("advocate")
    assert len({citizen.objective, police.objective, advocate.objective}) == 3
    assert "plain language" in profile_prompt("citizen")
    assert "chain-of-custody" in profile_prompt("police")
    assert "adverse authority" in profile_prompt("advocate")


@pytest.mark.parametrize(
    ("role", "query", "case_id", "expected"),
    [
        ("citizen", "What are my fundamental rights under Article 14?", None, "rights_explainer"),
        ("police", "How should electronic evidence authenticity be preserved?", None, "evidence_integrity"),
        ("police", "Search the private evidence in this case", "case-1", "case_evidence_search"),
        ("advocate", "Compare and distinguish the relevant precedents", None, "precedent_comparator"),
        ("advocate", "Identify contradictions and admissibility issues in the evidence", None, "evidence_challenge"),
    ],
)
def test_query_selects_a_real_role_specialist(role: str, query: str, case_id: str | None, expected: str) -> None:
    assert select_specialist_agent(role, query, case_id).id == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "expected_collection"),
    [("police", POLICE_CASE_DATA), ("advocate", ADVOCATE_CASE_DATA)],
)
async def test_professional_deep_retrieval_combines_gold_with_only_its_role_collection(
    role: str, expected_collection: str
) -> None:
    service = CapturingRetrieval()
    result = await retrieval_node(state(role, "case-123"), service)  # type: ignore[arg-type]
    assert [target.collection_name for target in service.targets] == [GLOBAL_LEGAL_CORPUS, expected_collection]
    assert service.targets[1].filters.case_ids == ["case-123"]
    assert result["agent_trace"][-1].details["case_scope_applied"] is True


@pytest.mark.asyncio
async def test_citizen_retrieval_never_targets_private_case_collections() -> None:
    service = CapturingRetrieval()
    result = await retrieval_node(state("citizen", "case-123"), service)  # type: ignore[arg-type]
    assert [target.collection_name for target in service.targets] == [GLOBAL_LEGAL_CORPUS]
    assert result["agent_trace"][-1].details["case_scope_applied"] is False
