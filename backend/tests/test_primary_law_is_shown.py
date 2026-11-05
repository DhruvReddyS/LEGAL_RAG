"""Primary law found for a question takes its place in what the reader sees."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.fast_research import STATUTES_READ_CLOSELY, governing_statutes, shown_to_the_reader


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


class _Reader:
    """Scores by a word in the passage, as a stand-in for reading it."""

    def __init__(self, *, broken: bool = False) -> None:
        self.broken = broken
        self.reads: list[int] = []

    async def relevance_scores(self, query, texts):
        if self.broken:
            raise RuntimeError("reranker unavailable")
        self.reads.append(len(texts))
        return [0.9 if "ANSWER" in text else 0.01 for text in texts]


async def _statutes(hits, query="Can police arrest without warrant?", reader=None):
    return await governing_statutes(
        reader or _Reader(),
        hits,
        query=query,
        focus_tokens={"arrest", "warrant", "police"},
        distinctive_terms=set(),
    )


def _unrelated(chunk: str, text: str = "Nothing in common with what was asked."):
    hit = _hit(chunk, chunk)
    hit.payload["text"] = text
    return hit


async def test_two_places_at_most() -> None:
    assert len(await _statutes([_hit(str(n), str(n)) for n in range(5)])) == 2


async def test_circulars_do_not_count_as_primary_law() -> None:
    assert await _statutes([_hit("x", "x", document_type="sop_or_circular")]) == []


async def test_the_constitution_counts() -> None:
    assert await _statutes([_hit("x", "x", document_type="other", source_type="CONSTITUTION")])


async def test_close_reading_finds_a_section_in_other_words() -> None:
    """The case this exists for: no shared words, and the right section."""
    found = await _statutes([_unrelated("wrong"), _unrelated("right", "ANSWER dishonour of cheque")])
    assert [hit.payload["chunk_id"] for hit in found] == ["right"]


async def test_nothing_is_shown_when_neither_test_passes() -> None:
    assert await _statutes([_unrelated("x")]) == []


async def test_a_lost_reranker_falls_back_to_the_word_gate() -> None:
    reader = _Reader(broken=True)
    assert [hit.payload["chunk_id"] for hit in await _statutes([_hit("x", "x"), _unrelated("y")], reader=reader)] == ["x"]


async def test_only_the_top_candidates_are_read() -> None:
    reader = _Reader()
    await _statutes([_unrelated(str(n)) for n in range(30)], reader=reader)
    assert reader.reads == [STATUTES_READ_CLOSELY]


async def test_a_foreign_law_question_gets_no_statute() -> None:
    hit = _unrelated("x", "ANSWER")
    assert await _statutes([hit], query="Can police arrest without warrant in Canada?") == []
