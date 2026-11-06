"""A confirmed law addresses the question, and a refusal costs no model time."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents import retrieval_agent
from app.agents.orchestrator import LegalRAGWorkflow
from app.agents.reasoning_agent import format_evidence
from app.agents.response_generation import _correct_act_names, _renumbered_lines


def _hit(chunk: str, relation: str | None = None) -> SimpleNamespace:
    payload = {"chunk_id": chunk, "text": "text", "section": "303", "document_type": "bare_act"}
    if relation:
        payload["retrieval_enrichment_relation"] = relation
    return SimpleNamespace(payload=payload)


@pytest.mark.asyncio
async def test_a_confirmed_section_already_in_hand_still_counts_as_confirmed(monkeypatch) -> None:
    section = _hit("s303")

    async def confirmed(*_args, **_kwargs):
        return [section], frozenset()

    async def no_terms():
        return []

    async def found(*_args, **_kwargs):
        return [section]

    monkeypatch.setattr(retrieval_agent, "governing_statutes", confirmed)
    service = SimpleNamespace(search_statutes=found)
    import asyncio

    new, was_confirmed, _ = await retrieval_agent._statutes_for(
        service, "q", "q", [section], asyncio.ensure_future(no_terms())
    )
    assert new == []
    assert was_confirmed is True


@pytest.mark.asyncio
async def test_a_section_read_and_ruled_out_is_named_by_its_act_and_section(monkeypatch) -> None:
    read = _hit("prisons-a")
    read.payload.update(act_name="Model Prisons Act", section="41")

    async def rules_it_out(*_args, **_kwargs):
        return [], frozenset({"prisons-a"})

    async def no_terms():
        return []

    async def found(*_args, **_kwargs):
        return [read]

    monkeypatch.setattr(retrieval_agent, "governing_statutes", rules_it_out)
    monkeypatch.setattr(retrieval_agent, "act_the_results_agree_on", lambda _hits: [])
    import asyncio

    _, _, moot = await retrieval_agent._statutes_for(
        SimpleNamespace(search_statutes=found), "q", "q", [], asyncio.ensure_future(no_terms())
    )
    assert moot == {("Model Prisons Act", "41")}


def test_a_question_the_evidence_does_not_address_skips_the_model() -> None:
    route = LegalRAGWorkflow._route_after_retrieval
    assert route({"evidence_addresses_question": False, "retry_count": 0}) == "skip"
    assert route({"evidence_addresses_question": True, "retry_count": 0}) == "reason"


def test_the_governing_provision_is_marked_for_the_model_and_nothing_else_is() -> None:
    text = format_evidence([_hit("bridge", "implementation_bridge"), _hit("other")])
    assert text.count("GOVERNS_THIS_QUESTION: yes") == 1
    assert text.index("GOVERNS_THIS_QUESTION") < text.index("SOURCE: S2")


@pytest.mark.parametrize("wrong", ["Nagariya", "Nagari", "Nagrik", "Nagarik"])
def test_the_sanhitas_name_is_always_spelt_correctly(wrong: str) -> None:
    assert _correct_act_names(f"Section 35 of the Bharatiya {wrong} Suraksha Sanhita, 2023") == (
        "Section 35 of the Bharatiya Nagarik Suraksha Sanhita, 2023"
    )


def test_a_refusal_with_no_model_run_still_gives_a_clean_answer() -> None:
    from app.agents.response_generation import response_generation_node
    from app.services.generation import INSUFFICIENT_EVIDENCE

    result = response_generation_node(
        {
            "query": "q",
            "role": "citizen",
            "evidence_addresses_question": False,
            "verification_result": None,
            "retrieved_chunks": [],
            "stage_metrics": [],
            "agent_trace": [],
        }
    )
    assert result["final_answer"] == INSUFFICIENT_EVIDENCE
    assert result["citations"] == []


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Ravi parked his motorcycle outside his shop. It was missing at 7 am.", "motorcycle"),
        ("Someone stole my gold chain at the market.", "gold chain"),
    ],
)
def test_the_missing_property_is_recovered_from_plain_words(description: str, expected: str) -> None:
    from app.agents.drafting_agent import recover_explicit_missing_item
    from app.schemas.documents import FIRFacts

    assert recover_explicit_missing_item(FIRFacts(narrative=description), description).subject_or_property == expected


def test_nothing_is_recovered_when_nothing_is_missing() -> None:
    from app.agents.drafting_agent import recover_explicit_missing_item
    from app.schemas.documents import FIRFacts

    facts = recover_explicit_missing_item(FIRFacts(narrative="x"), "He parked his car outside the court and went in.")
    assert facts.subject_or_property is None


def test_no_renumbered_provision_is_left_out_however_many_a_judgment_cites() -> None:
    moved = {
        "IEA s.3": ["BSA s.2 (the elements of the provision also changed)"],
        "IEA s.5": ["BSA s.3"],
        "IEA s.65": ["BSA s.60"],
        "IEA s.65A": ["BSA s.62"],
        "IEA s.65B": ["BSA s.63 (the elements of the provision also changed)"],
    }
    lines = _renumbered_lines(moved)
    for old, new in moved.items():
        assert f"{old} is now {new[0]}" in lines
    assert lines.splitlines()[0].startswith("- IEA s.3 is now")
    assert len(lines.splitlines()) == 4
