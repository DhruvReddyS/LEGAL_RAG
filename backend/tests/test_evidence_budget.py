"""Primary law is read whole, within a budget the prompt can hold."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.evidence_budget import (
    DEFAULT_CHARACTERS,
    PRIMARY_LAW_CHARACTERS,
    PRIMARY_LAW_TOTAL_CHARACTERS,
    SHARING_CHARACTERS,
    character_limits,
)
from app.agents.reasoning_agent import format_evidence
from app.agents.verification_agent import build_premises
from app.services.retrieval import RetrievalHit


def _hit(chunk: str, length: int, document_type: str = "bare_act") -> SimpleNamespace:
    return SimpleNamespace(payload={"chunk_id": chunk, "text": "x" * length, "document_type": document_type})


def test_a_long_section_is_read_to_the_end() -> None:
    assert character_limits([_hit("s35", 5544)])["s35"] == 5544


def test_a_very_long_section_is_still_capped() -> None:
    assert character_limits([_hit("long", 30000)])["long"] == PRIMARY_LAW_CHARACTERS


def test_without_primary_law_nothing_changes() -> None:
    limits = character_limits([_hit("a", 9000, "judgment"), _hit("b", 9000, "sop_or_circular")])
    assert set(limits.values()) == {DEFAULT_CHARACTERS}


def test_other_material_gives_way_to_primary_law() -> None:
    limits = character_limits([_hit("act", 3000), _hit("judgment", 9000, "judgment")])
    assert limits == {"act": 3000, "judgment": SHARING_CHARACTERS}


def test_the_total_for_primary_law_holds_and_the_highest_ranked_comes_first() -> None:
    limits = character_limits([_hit(str(n), 9000) for n in range(6)])
    assert limits["0"] == PRIMARY_LAW_CHARACTERS
    assert limits["5"] == SHARING_CHARACTERS
    assert sum(limits[str(n)] for n in range(2)) <= PRIMARY_LAW_TOTAL_CHARACTERS


def test_the_constitution_counts_as_primary_law() -> None:
    hit = SimpleNamespace(payload={"chunk_id": "c", "text": "x" * 4000, "source_type": "CONSTITUTION"})
    assert character_limits([hit])["c"] == 4000


def _retrieval_hit(chunk: str, text: str) -> RetrievalHit:
    return RetrievalHit(
        point_id=chunk,
        payload={"chunk_id": chunk, "text": text, "document_type": "bare_act", "title": "BNSS"},
        dense_score=0.9,
        sparse_score=0.1,
        fused_score=0.9,
        reranker_score=0.9,
    )


def test_the_model_and_the_verifier_both_see_the_end_of_a_long_list() -> None:
    text = "ground " * 500 + "(g) deserter from the Armed Forces"
    hit = _retrieval_hit("s35", text)
    assert "deserter" in format_evidence([hit])
    premises, truncated = build_premises([hit])
    assert "deserter" in premises["s35"]
    assert truncated == 0
