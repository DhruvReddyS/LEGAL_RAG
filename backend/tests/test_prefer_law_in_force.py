"""Ordering when a repealed provision and a live one both match.

The corpus holds 5,387 chunks of the repealed IPC, CrPC and Evidence Act
against 1,026 of the Sanhitas that replaced them on 1 July 2024. Retrieval is
volume-sensitive, so the repealed provision wins on weight of material rather
than on being the law.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.retrieval import RetrievalHit, _prefer_law_in_force


def _hit(chunk_id: str, act_name: str, score: float) -> RetrievalHit:
    return RetrievalHit(
        point_id=chunk_id,
        payload={"chunk_id": chunk_id, "act_name": act_name, "text": "x"},
        dense_score=score,
        sparse_score=None,
        fused_score=score,
        reranker_score=score,
    )


BNSS = "THE BHARATIYA NAGARIK SURAKSHA SANHITA, 2023"
CRPC = "The Code of Criminal Procedure, 1973 (Act No.2 of 1974)"


class TestTheLiveProvisionIsPreferred:
    def test_a_close_repealed_match_gives_way(self) -> None:
        ordered = _prefer_law_in_force(
            [_hit("crpc-1", CRPC, 0.90), _hit("bnss-1", BNSS, 0.88)]
        )

        assert [hit.point_id for hit in ordered] == ["bnss-1", "crpc-1"]

    def test_a_clearly_better_repealed_match_still_wins(self) -> None:
        """The old codes still govern conduct from before the repeal, so the
        preference is a nudge and not a veto. A repealed provision that beats
        the live one by more than the penalty keeps its place."""
        hits = [_hit("crpc-top", CRPC, 0.99)]
        hits += [_hit(f"bnss-{i}", BNSS, 0.90 - i * 0.01) for i in range(5)]

        ordered = _prefer_law_in_force(hits)

        assert ordered[0].point_id == "bnss-0"
        assert "crpc-top" in [hit.point_id for hit in ordered[:4]]

    def test_relevance_order_is_kept_among_live_provisions(self) -> None:
        ordered = _prefer_law_in_force(
            [_hit("b", BNSS, 0.70), _hit("a", BNSS, 0.90), _hit("c", BNSS, 0.50)]
        )

        assert [hit.point_id for hit in ordered] == ["a", "b", "c"]

    def test_documents_that_are_not_acts_are_unaffected(self) -> None:
        """An advisory *about* a repealed section is not itself repealed."""
        ordered = _prefer_law_in_force(
            [
                _hit("advisory", "Advisory on misuse of section 498A IPC", 0.90),
                _hit("bnss-1", BNSS, 0.80),
            ]
        )

        assert ordered[0].point_id == "advisory"

    def test_the_payload_field_is_honoured_when_present(self) -> None:
        """A rebuilt index carries `replaced_by`; an older one does not, and
        the Act name is read instead so both behave the same."""
        repealed = _hit("x", "Some Act Not In The Table, 1950", 0.90)
        repealed.payload["replaced_by"] = "The Replacement Act, 2023"
        ordered = _prefer_law_in_force([repealed, _hit("live", BNSS, 0.88)])

        assert ordered[0].point_id == "live"


class TestThePreferenceCanBeTurnedOff:
    def test_a_zero_penalty_leaves_relevance_order_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "repealed_rank_penalty", 0)

        ordered = _prefer_law_in_force(
            [_hit("crpc-1", CRPC, 0.90), _hit("bnss-1", BNSS, 0.88)]
        )

        assert [hit.point_id for hit in ordered] == ["crpc-1", "bnss-1"]

    def test_an_empty_result_set_is_safe(self) -> None:
        assert _prefer_law_in_force([]) == []
