"""The evaluation harness has to be right before its numbers mean anything."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.golden_set import (
    GoldenItem,
    ItemResult,
    RelevantSource,
    load_golden_set,
    score,
)

GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "data" / "legal_kb" / "evaluation" / "golden_set_v1.json"
)


class TestMetrics:
    def _result(self, ranks: list[int], specs: int = 2) -> ItemResult:
        item = GoldenItem(
            id="x", question="q", expectation="answer",
            relevant=tuple(RelevantSource(contains=str(n)) for n in range(specs)),
        )
        return ItemResult(item=item, ranks=ranks, retrieved=20)

    def test_ndcg_never_exceeds_one(self) -> None:
        """One relevance spec can match many chunks.

        An earlier denominator counted specs rather than matches, so gain
        outran the ideal and nDCG reported above 1.0 — impossible by
        definition, and it made the whole column meaningless.
        """
        for ranks in ([1], [1, 2], [1, 2, 3, 4, 5], list(range(1, 11))):
            assert 0.0 <= self._result(ranks).ndcg_at(10) <= 1.0, ranks

    def test_ndcg_is_one_when_matches_are_at_the_top(self) -> None:
        assert self._result([1, 2, 3]).ndcg_at(10) == pytest.approx(1.0)

    def test_ndcg_falls_when_matches_rank_lower(self) -> None:
        assert self._result([5, 6, 7]).ndcg_at(10) < self._result([1, 2, 3]).ndcg_at(10)

    def test_recall_is_binary_on_finding_any_correct_source(self) -> None:
        result = self._result([7])
        assert result.recall_at(5) == 0.0
        assert result.recall_at(20) == 1.0

    def test_reciprocal_rank(self) -> None:
        assert self._result([3]).reciprocal_rank() == pytest.approx(1 / 3)
        assert self._result([]).reciprocal_rank() == 0.0


class TestRelevanceMatching:
    def test_a_source_survives_rechunking(self) -> None:
        """Relevance is expressed against stable things, never chunk IDs.

        Chunk IDs are content-addressed, so they all change on a re-chunk —
        which is exactly when this set is needed.
        """
        source = RelevantSource(act="constitution", section="14")
        assert source.matches(
            {"act_name": "The Constitution of India", "section": "14",
             "chunk_id": "gold-chunk-anything"}
        )
        assert source.matches(
            {"act_name": "The Constitution of India", "section": "14",
             "chunk_id": "gold-chunk-completely-different"}
        )

    def test_every_named_field_must_match(self) -> None:
        source = RelevantSource(act="constitution", section="14")
        assert not source.matches({"act_name": "Constitution", "section": "21"})
        assert not source.matches({"act_name": "Evidence Act", "section": "14"})

    def test_an_unset_field_is_not_checked(self) -> None:
        assert RelevantSource(section="14").matches({"section": "14", "title": "any"})

    def test_phrase_matching_is_case_insensitive(self) -> None:
        assert RelevantSource(contains="Equality Before The Law").matches(
            {"text": "...equality before the law or the equal protection..."}
        )


class TestGoldenSetFile:
    def test_it_loads_and_validates(self) -> None:
        items = load_golden_set(GOLDEN)
        assert len(items) >= 20

    def test_answerable_items_name_a_source(self) -> None:
        for item in load_golden_set(GOLDEN):
            if item.expectation == "answer":
                assert item.relevant, item.id

    def test_abstention_items_name_none(self) -> None:
        """An abstention item with sources is not testing abstention."""
        for item in load_golden_set(GOLDEN):
            if item.expectation == "abstain":
                assert not item.relevant, item.id
                assert item.note, f"{item.id}: an expected gap needs its reason recorded"

    def test_no_item_pins_to_a_chunk_id(self) -> None:
        raw = json.loads(GOLDEN.read_text(encoding="utf-8"))
        assert "chunk_id" not in json.dumps(raw)

    def test_duplicate_ids_are_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "dupes.json"
        path.write_text(
            json.dumps(
                {"items": [
                    {"id": "a", "question": "q", "expectation": "abstain", "note": "n"},
                    {"id": "a", "question": "q2", "expectation": "abstain", "note": "n"},
                ]}
            )
        )
        with pytest.raises(ValueError, match="duplicate"):
            load_golden_set(path)


def test_scoring_records_every_matching_rank() -> None:
    item = GoldenItem(
        id="x", question="q", expectation="answer",
        relevant=(RelevantSource(contains="equality"),),
    )
    payloads = [{"text": "unrelated"}, {"text": "equality before law"}, {"text": "equality again"}]
    assert score(item, payloads).ranks == [2, 3]
