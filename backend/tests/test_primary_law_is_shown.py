"""Primary law found for a question takes its place in what the reader sees."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.fast_research import governing_statutes, shown_to_the_reader


def _hit(chunk: str, document: str, *, relation: str | None = None, document_type: str = "bare_act", source_type: str = "ACT"):
    return SimpleNamespace(
        point_id=chunk,
        payload={
            "chunk_id": chunk,
            "canonical_document_id": document,
            "document_type": document_type,
            "source_type": source_type,
            "text": "arrest arrest without warrant police officer",
            "retrieval_enrichment_relation": relation,
        },
    )


def test_the_order_is_bridge_then_statute_then_forwarded_then_the_rest() -> None:
    shown = shown_to_the_reader(
        [_hit("ranked", "a")],
        [_hit("forwarded", "b", relation="citation_forwarding"), _hit("bridge", "c", relation="implementation_bridge")],
        [_hit("statute", "d")],
        limit=4,
    )
    assert [hit.payload["chunk_id"] for hit in shown] == ["bridge", "statute", "forwarded", "ranked"]


def test_one_passage_per_document_still_holds() -> None:
    shown = shown_to_the_reader([_hit("ranked", "same")], [], [_hit("statute", "same")], limit=4)
    assert [hit.payload["chunk_id"] for hit in shown] == ["statute"]


def test_the_limit_holds() -> None:
    assert len(shown_to_the_reader([_hit(str(n), str(n)) for n in range(9)], [], [], limit=4)) == 4


def _statutes(hits, query="Can police arrest without warrant?"):
    return governing_statutes(
        hits, query=query, focus_tokens={"arrest", "warrant", "police"}, distinctive_terms=set()
    )


def test_two_places_at_most() -> None:
    assert len(_statutes([_hit(str(n), str(n)) for n in range(5)])) == 2


def test_circulars_do_not_count_as_primary_law() -> None:
    assert _statutes([_hit("x", "x", document_type="sop_or_circular")]) == []


def test_the_constitution_counts() -> None:
    assert _statutes([_hit("x", "x", document_type="other", source_type="CONSTITUTION")])


def test_the_relevance_gate_still_applies() -> None:
    hit = _hit("x", "x")
    hit.payload["text"] = "Nothing to do with the question at all."
    assert _statutes([hit]) == []


def test_a_foreign_law_question_gets_no_statute() -> None:
    assert _statutes([_hit("x", "x")], query="Can police arrest without warrant in Canada?") == []
