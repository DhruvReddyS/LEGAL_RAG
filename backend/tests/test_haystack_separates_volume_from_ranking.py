"""The haystack report must not report corpus growth as a retrieval change.

v5 holds roughly twice v4's points. Every recall and citation number will move
on that alone, and the decision a gate drives depends on which happened: a
volume effect means the metric moved and the system did not.

These tests pin the three ways the count could mislead -- counting text the
index never received, counting one document twice, and counting a grouped
canonical id as though it were one citable document.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "golden_set_haystack_report", ROOT / "scripts" / "golden_set_haystack_report.py"
)
assert SPEC and SPEC.loader
haystack = importlib.util.module_from_spec(SPEC)
sys.modules["golden_set_haystack_report"] = haystack
SPEC.loader.exec_module(haystack)


def write_store(root: Path, name: str, documents: dict[str, list[dict]]) -> Path:
    """A per-version chunk store, keyed by canonical id as the pipeline writes it."""
    store = root / f"chunks.{name}"
    store.mkdir(parents=True)
    for canonical_id, records in documents.items():
        lines = [
            json.dumps({"canonical_document_id": canonical_id, "quality": "indexed", **record})
            for record in records
        ]
        (store / f"{canonical_id}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return store


def test_a_chunk_the_index_rejected_is_not_part_of_the_haystack(tmp_path):
    """The store is written after the quality filter today. If that ever changes,
    rejected text must not count: no query can reach it, so counting it would
    show as corpus growth that retrieval cannot use."""
    store = tmp_path / "chunks.v"
    store.mkdir()
    (store / "doc-a.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"document_id": "d1", "quality": "indexed", "text": "reasonable restrictions apply"}),
                json.dumps({"document_id": "d2", "quality": "citation_furniture", "text": "reasonable restrictions apply"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    items = [("q1", "question", ["reasonable restrictions"])]
    counts = haystack.count_matches(store, items)

    assert counts["items"]["q1"]["documents"] == 1, "the rejected chunk was counted"
    assert counts["items"]["q1"]["chunks"] == 1
    assert counts["corpus"]["chunks"] == 1


def test_two_phrases_in_one_chunk_count_the_chunk_once(tmp_path):
    """Several golden-set items list a section number and the phrase it contains.
    Summing per-phrase counts would count a document holding both twice, so a
    corpus that was only re-chunked would look like it had grown."""
    store = tmp_path / "chunks.v"
    store.mkdir()
    (store / "doc-a.jsonl").write_text(
        json.dumps(
            {
                "document_id": "d1",
                "quality": "indexed",
                "text": "section 19(1)(a) permits reasonable restrictions",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    items = [("q1", "question", ["section 19(1)(a)", "reasonable restrictions"])]
    counts = haystack.count_matches(store, items)

    assert counts["items"]["q1"]["documents"] == 1
    assert counts["items"]["q1"]["chunks"] == 1, "one chunk was counted twice"


def test_the_haystack_is_counted_at_citation_granularity(tmp_path):
    """The filename is the canonical id, which groups duplicates of one
    instrument. The same Act from two ministries is one canonical id and two
    documents with two official URLs, and citations are at document
    granularity, so the haystack has to be."""
    store = tmp_path / "chunks.v"
    store.mkdir()
    (store / "canonical-act.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"document_id": "ministry-a-copy", "quality": "indexed", "text": "reasonable restrictions"}),
                json.dumps({"document_id": "ministry-b-copy", "quality": "indexed", "text": "reasonable restrictions"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    counts = haystack.count_matches(store, [("q1", "question", ["reasonable restrictions"])])

    assert counts["items"]["q1"]["documents"] == 2, (
        "two separately citable copies collapsed into the canonical group"
    )


def test_an_item_whose_haystack_doubled_is_not_attributable_to_retrieval(tmp_path, monkeypatch):
    """The whole point: recall moving on an item that went from one matching
    document to four says nothing about ranking, and the report has to say so
    rather than leaving a reader to infer it."""
    write_store(tmp_path, "global_legal_corpus_vbefore", {
        "c-easy": [{"document_id": "d1", "text": "bail is a matter of discretion"}],
        "c-hard": [{"document_id": "d2", "text": "the limitation period is three years"}],
    })
    write_store(tmp_path, "global_legal_corpus_vafter", {
        # The easy item's phrase is now in four documents.
        "c-easy": [{"document_id": "d1", "text": "bail is a matter of discretion"}],
        "c-easy-2": [{"document_id": "d3", "text": "bail is a matter of discretion"}],
        "c-easy-3": [{"document_id": "d4", "text": "bail is a matter of discretion"}],
        "c-easy-4": [{"document_id": "d5", "text": "bail is a matter of discretion"}],
        # The hard item's is still in exactly one.
        "c-hard": [{"document_id": "d2", "text": "the limitation period is three years"}],
    })
    golden = tmp_path / "golden.json"
    golden.write_text(
        json.dumps(
            [
                {"id": "easy", "question": "bail?", "relevant": [{"contains": "Bail is a matter of discretion"}]},
                {"id": "hard", "question": "limitation?", "relevant": [{"contains": "limitation period is three years"}]},
                {"id": "absent", "question": "missing?", "relevant": [{"contains": "no document says this"}]},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(haystack, "CHUNK_ROOT", tmp_path)
    monkeypatch.setattr(haystack, "GOLDEN", golden)

    result = haystack.report("vbefore", "vafter")
    rows = {row["id"]: row for row in result["rows"]}

    assert rows["easy"]["growth"] == 4.0
    assert rows["easy"]["recall_change_attributable_to_retrieval"] is False
    assert rows["hard"]["growth"] == 1.0
    assert rows["hard"]["recall_change_attributable_to_retrieval"] is True
    assert rows["absent"]["still_absent"] is True
    assert rows["absent"]["growth"] is None, "a zero baseline is not a growth ratio"

    assert result["summary"]["items_where_recall_change_is_attributable"] == 1
    assert result["summary"]["items_whose_haystack_grew"] == 1
    assert result["summary"]["items_still_absent"] == 1
    # The absent item has no before baseline, so it belongs in neither of the
    # first two buckets. Folding it into "grew" would report an item nothing
    # matches as an item that got easier.
    assert result["summary"]["items_with_no_before_baseline"] == 1


def test_phrase_matching_ignores_the_case_the_golden_set_was_written_in(tmp_path, monkeypatch):
    """The golden set writes predicates in prose capitalisation; the corpus
    uses whatever the gazette used. A case-sensitive match would report a
    provision as absent while it sits in the index."""
    write_store(tmp_path, "global_legal_corpus_vbefore", {
        "c1": [{"document_id": "d1", "text": "REASONABLE RESTRICTIONS in the interest of public order"}],
    })
    write_store(tmp_path, "global_legal_corpus_vafter", {
        "c1": [{"document_id": "d1", "text": "REASONABLE RESTRICTIONS in the interest of public order"}],
    })
    golden = tmp_path / "golden.json"
    golden.write_text(
        json.dumps([{"id": "x", "question": "q", "relevant": [{"contains": "Reasonable Restrictions"}]}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(haystack, "CHUNK_ROOT", tmp_path)
    monkeypatch.setattr(haystack, "GOLDEN", golden)

    row = haystack.report("vbefore", "vafter")["rows"][0]
    assert row["documents_after"] == 1
    assert row["still_absent"] is False


def test_the_real_golden_set_yields_phrase_predicates():
    """Guards the shape this tool depends on. The golden set's predicates are
    phrases rather than document ids -- the documented weakness this report
    exists to work around -- so if it ever gains real identities, this report
    should be replaced rather than quietly kept."""
    if not haystack.GOLDEN.exists():
        pytest.skip("golden set not present")
    items = haystack.golden_phrases()
    assert items, "no phrase predicates found; has the golden set changed shape?"
    for item_id, _question, phrases in items:
        assert item_id and item_id != "None"
        assert all(phrase == phrase.casefold() for phrase in phrases)
