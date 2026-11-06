"""A confirmed law addresses the question, and a refusal costs no model time."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents import retrieval_agent
from app.services.fast_research import distinct_provisions, governing_statutes, shown_to_the_reader
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
    assert moot == {("model prisons act", "41")}


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


def test_one_act_filed_under_two_names_is_one_provision() -> None:
    letter = _hit("a")
    letter.payload.update(act_name="Model Prisons and Correctional Services Act, 2023 - Letter to States and UTs", section="41")
    act = _hit("b")
    act.payload.update(act_name="Model Prisons and Correctional Services Act", section="41")
    assert retrieval_agent._provision_of(letter) == retrieval_agent._provision_of(act)


def _statute(chunk: str, relation: str | None = None, act: str = "Some Special Act", section: str = "1") -> SimpleNamespace:
    hit = _hit(chunk, relation)
    hit.payload.update(document_type="bare_act", act_name=act, title=act, section=section, text=chunk)
    return hit


def _theft() -> SimpleNamespace:
    return _statute("s303", "implementation_bridge", act="The Bharatiya Nyaya Sanhita, 2023", section="303")


def _scoring(*scores: float) -> SimpleNamespace:
    calls: list[list[str]] = []

    async def relevance_scores(_query, texts):
        calls.append(texts)
        return list(scores)

    return SimpleNamespace(relevance_scores=relevance_scores, calls=calls)


def _copy(chunk: str, act: str, text: str, section: str = "6") -> SimpleNamespace:
    hit = _statute(chunk, act=act, section=section)
    hit.payload["text"] = text
    return hit


RTI_6 = "6. Request for obtaining information. A person who desires to obtain any information under this Act"
RTI_7 = "7. Disposal of request. The Central Public Information Officer shall within thirty days of the receipt"


def test_a_second_edition_of_a_section_gives_way_to_the_next_section() -> None:
    first, copy, next_section = (
        _copy("a", "The Right to Information Act, 2005", RTI_6),
        _copy("b", "Rti 2005", "6. (1) " + RTI_6[3:]),
        _copy("c", "The Right to Information Act, 2005", RTI_7, section="7"),
    )
    assert distinct_provisions([first, copy, next_section]) == [first, next_section]


def test_the_properly_named_copy_is_kept_in_the_first_place() -> None:
    poor, good = _copy("a", "Rti 2005", RTI_6), _copy("b", "The Right to Information Act, 2005", RTI_6)
    assert distinct_provisions([poor, good]) == [good]


def test_the_same_number_in_another_act_is_a_different_provision() -> None:
    hits = [_copy("a", "An Act", RTI_6), _copy("b", "Other Act", "6. Duties of the licensing authority upon a vehicle")]
    assert distinct_provisions(hits) == hits


def test_two_chunks_of_one_long_section_both_stay() -> None:
    hits = [_copy("a", "An Act", RTI_6), _copy("b", "An Act", "continued proviso regarding fees and persons below poverty line")]
    assert distinct_provisions(hits) == hits


def test_material_with_no_section_is_not_compared() -> None:
    hits = [_copy("a", "A", RTI_6, section=""), _copy("b", "A", RTI_6, section="")]
    assert distinct_provisions(hits) == hits


def test_outside_a_case_no_file_text_reaches_the_concepts() -> None:
    assert retrieval_agent._what_the_files_name([_statute("law")]) == ""


def test_in_a_case_the_files_can_name_the_offence() -> None:
    case_file = _hit("file")
    case_file.payload.update(case_id="c1", text="Alleged offence: theft of a motorcycle.")
    assert "theft" in retrieval_agent._what_the_files_name([_statute("law"), case_file])


@pytest.mark.asyncio
async def test_the_deep_lane_reads_every_copy_it_was_measured_on() -> None:
    first, copy = _copy("a", "An Act", RTI_6), _copy("b", "Rti 2005", RTI_6)
    service = _scoring(0.9, 0.9)
    await governing_statutes(service, [first, copy], query="q", focus_tokens=set(), distinctive_terms=set())
    assert len(service.calls[0]) == 2


def test_two_chosen_sections_of_one_act_both_show() -> None:
    first, second = _statute("s35", "implementation_bridge", section="35"), _statute("s34", "implementation_bridge", section="34")
    first.payload.update(document_id="one-act", text="35. A complaint may be filed with a District Commission")
    second.payload.update(document_id="one-act", text="34. The District Commission shall have jurisdiction over value")
    assert shown_to_the_reader([], [first, second], [], limit=4) == [first, second]


def test_a_stated_limit_on_what_is_shown_still_holds() -> None:
    hits = [_copy(str(index), "An Act", f"{index}. unique words number {index} about subject {index * 7}", section=str(index)) for index in range(6)]
    assert len(shown_to_the_reader(hits, [], [], limit=4)) <= 4


def _consumer() -> SimpleNamespace:
    return _statute("s35", "implementation_bridge", act="The Consumer Protection Act, 2019", section="35")


def _titled(chunk: str, title: str, document_type: str = "commentary") -> SimpleNamespace:
    hit = _hit(chunk)
    hit.payload.update(document_type=document_type, act_name=title, title=title, section="3", text=chunk)
    return hit


def test_the_act_a_governing_section_replaced_does_not_reach_the_model() -> None:
    current = _consumer()
    hits = [
        current,
        _titled("old", "The Consumer Protection Act, 1986 (repealed by the Consumer Protection Act, 2019)", "bare_act"),
        _titled("notes", "Commentary on the Consumer Protection Act, 1986, published by the Commission"),
    ]
    assert retrieval_agent._without_the_act_it_replaced("My phone broke", hits) == [current]


def test_the_rest_of_the_list_is_not_touched_by_the_earlier_act_rule() -> None:
    current = _consumer()
    hits = [
        current,
        _statute("same-act", act="The Consumer Protection Act, 2019", section="2"),
        _titled("other", "The Sale of Goods Act, 1930", "bare_act"),
        _titled("case", "A v B on the Consumer Protection Act, 1986", "judgment"),
    ]
    assert retrieval_agent._without_the_act_it_replaced("My phone broke", hits) == hits


def test_asking_about_the_old_act_by_its_year_keeps_it() -> None:
    hits = [_consumer(), _titled("old", "The Consumer Protection Act, 1986", "bare_act")]
    assert retrieval_agent._without_the_act_it_replaced("What did the 1986 Act say?", hits) == hits


def test_without_a_governing_section_an_older_act_stays() -> None:
    hits = [
        _statute("new", act="The Consumer Protection Act, 2019", section="35"),
        _titled("old", "The Consumer Protection Act, 1986", "bare_act"),
    ]
    assert retrieval_agent._without_the_act_it_replaced("My phone broke", hits) == hits


def test_an_act_named_only_in_brackets_does_not_match_every_other_act() -> None:
    hits = [
        _statute(
            "sc",
            "implementation_bridge",
            act="The Scheduled Castes and the Scheduled Tribes (Prevention of Atrocities) Act, 1989",
            section="14",
        ),
        _titled("other", "The Protection of Civil Rights Act, 1955", "bare_act"),
    ]
    assert retrieval_agent._without_the_act_it_replaced("Which court?", hits) == hits


@pytest.mark.asyncio
async def test_with_the_governing_section_known_a_statute_that_does_not_answer_goes() -> None:
    theft, prisons = _theft(), _statute("s41", act="Model Prisons Act", section="41")
    judgment = _hit("judgment")
    judgment.payload["document_type"] = "judgment"
    kept = await retrieval_agent._statutes_that_answer(_scoring(0.002), "q", [theft, prisons, judgment])
    assert kept == [theft, judgment]


@pytest.mark.asyncio
async def test_a_statute_that_also_answers_stays() -> None:
    theft, related = _theft(), _statute("related")
    assert await retrieval_agent._statutes_that_answer(_scoring(0.8), "q", [theft, related]) == [theft, related]


@pytest.mark.asyncio
async def test_without_a_governing_section_the_list_is_left_alone() -> None:
    hits = [_statute("a"), _statute("b", section="2")]
    service = _scoring(0.0, 0.0)
    assert await retrieval_agent._statutes_that_answer(service, "q", hits) == hits
    assert service.calls == []


@pytest.mark.asyncio
async def test_the_governing_act_and_the_general_codes_cost_no_reading() -> None:
    hits = [
        _theft(),
        _statute("other", act="The Bharatiya Nyaya Sanhita, 2023", section="304"),
        _statute("crpc", act="The Code of Criminal Procedure, 1973", section="154"),
    ]
    service = _scoring()
    assert await retrieval_agent._statutes_that_answer(service, "q", hits) == hits
    assert service.calls == []


@pytest.mark.asyncio
async def test_a_provision_in_several_chunks_is_read_once_and_goes_together() -> None:
    hits = [_theft(), _statute("a", section="41"), _statute("b", section="41")]
    service = _scoring(0.0)
    assert await retrieval_agent._statutes_that_answer(service, "q", hits) == [hits[0]]
    assert len(service.calls[0]) == 1


@pytest.mark.asyncio
async def test_a_failed_reading_costs_nothing() -> None:
    async def down(_query, _texts):
        raise RuntimeError

    hits = [_theft(), _statute("b")]
    assert await retrieval_agent._statutes_that_answer(SimpleNamespace(relevance_scores=down), "q", hits) == hits
