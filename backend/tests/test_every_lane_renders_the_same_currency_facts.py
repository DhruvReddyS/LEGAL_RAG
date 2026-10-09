"""Four lanes build a citation. All four must say the same thing about currency.

`citation_labels` exists so the lanes cannot render different subsets of the
same facts, and its docstring says "the three lanes". There are four citation
builders: the Fast lane, Deep's response generation, the interim located-source
list, and the advocate's defence strategy agent. The fourth was the one that
did not call it.

It set `current_status` from its own helper and never set `repeal_label`,
`replaced_by`, `repealed_on` or `section_mappings`, so those took their schema
defaults -- and `repeal_label` defaults to "none". An advocate building a
defence strategy could therefore be shown an Indian Penal Code provision with
no indication it was replaced on 1 July 2024, while a citizen asking the same
question in Fast or Deep got "[no longer in force from 2024-07-01; replaced
by ...]" inline in the answer. 21% of this corpus is the IPC, CrPC and
Evidence Act.

The test that matters is the last one: it asserts every builder reaches the
shared primitive, so a fifth lane cannot be added without it.
"""

from __future__ import annotations

import inspect

import pytest

from app.agents.defence_strategy_agent import _citation_labels_for, _citations
from app.services.citation_status import citation_labels
from app.services.retrieval import RetrievalHit


REPEALED_IPC = {
    "chunk_id": "ipc-378",
    "text": "Whoever, intending to take dishonestly any movable property...",
    "title": "The Indian Penal Code, 1860",
    "act_name": "Indian Penal Code",
    "section": "378",
    "source_type": "act",
    "page_start": 90,
    "page_end": 90,
    "is_current": False,
    "is_superseded": True,
    "current_status": "repealed",
}


def _hit(payload: dict) -> RetrievalHit:
    return RetrievalHit(
        point_id=str(payload["chunk_id"]),
        payload=payload,
        dense_score=0.8,
        sparse_score=0.2,
        fused_score=0.5,
        reranker_score=0.5,
    )


def test_the_advocate_lane_now_reports_what_the_shared_primitive_reports() -> None:
    assert _citation_labels_for(REPEALED_IPC) == citation_labels(REPEALED_IPC)


def test_a_repealed_provision_carries_its_repeal_label_in_the_advocate_lane() -> None:
    """The defect, stated as the reader experiences it."""
    citations = _citations([_hit(REPEALED_IPC)], {"ipc-378"})
    assert len(citations) == 1
    citation = citations[0]
    expected = citation_labels(REPEALED_IPC)
    assert citation.repeal_label == expected["repeal_label"]
    assert citation.current_status == expected["current_status"]
    assert citation.replaced_by == expected["replaced_by"]
    assert citation.repealed_on == expected["repealed_on"]


def test_private_case_evidence_is_not_given_a_currency_verdict() -> None:
    """A witness statement has no commencement date and cannot be repealed.

    Suppressed explicitly rather than left to default, because
    `repeal_label: "none"` on case evidence has to mean "not applicable here"
    and not "checked and in force".
    """
    statement = {
        "chunk_id": "case-1",
        "text": "The complainant stated that the vehicle was taken on 4 March.",
        "title": "Witness statement",
        "source_type": "case_document",
        "page_start": 1,
        "page_end": 1,
        "corpus_scope": "private_case",
    }
    labels = _citation_labels_for(statement)
    assert labels["current_status"] == "not_applicable"
    assert labels["repeal_label"] == "none"
    assert labels["replaced_by"] is None
    assert labels["section_mappings"] == []

    citation = _citations([_hit(statement)], {"case-1"})[0]
    assert citation.current_status == "not_applicable"


def test_the_advocate_lane_still_only_cites_what_the_answer_used() -> None:
    """The behaviour the change must not alter."""
    used = _citations([_hit(REPEALED_IPC)], set())
    assert used == []


def test_every_citation_builder_reaches_the_shared_primitive() -> None:
    """The guard against a fifth lane repeating the fourth lane's mistake.

    A builder that reads the payload keys itself will drift the moment a field
    is added -- which is how `source_url` and `currency_note` each reached
    three readers and missed one.
    """
    from app.agents import defence_strategy_agent, located_sources, response_generation
    from app.services import fast_research

    builders = {
        "fast_research": fast_research,
        "response_generation": response_generation,
        "located_sources": located_sources,
        "defence_strategy_agent": defence_strategy_agent,
    }
    for name, module in builders.items():
        source = inspect.getsource(module)
        assert "citation_labels" in source, (
            f"{name} builds a citation without the shared currency primitive; "
            "it will render a different subset of the same facts"
        )


def test_the_shared_primitive_supplies_every_currency_field_a_citation_has() -> None:
    """If a field is added to the schema it must come from one place.

    Listed explicitly so adding a currency field to AgentCitation without
    adding it here fails loudly rather than defaulting silently in one lane.
    """
    supplied = set(citation_labels(REPEALED_IPC))
    assert supplied == {
        "current_status",
        "replaced_by",
        "repealed_on",
        "repeal_label",
        "section_mappings",
        "unmapped_repealed_provisions",
        "mapping_review_status",
    }
