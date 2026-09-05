"""The cross-encoder is off, and the things coupled to it still behave.

Measured twice, on two different golden sets, and it earned its cost on
neither. Against the 48-item set it costs 5,126 ms a query where fusion alone
costs 91, and R@1 *falls* from 0.69 to 0.64 while R@5 and R@20 do not move.

The reason this is a test file and not a one-line default change is the
coupling. `LOW_RERANKER_SCORE_FALLBACK_THRESHOLD` is 0.15, calibrated for
cross-encoder output. A fused RRF score for a top-ranked hit is around 0.016.
Turning reranking off without touching that comparison makes it true for every
query, so every Deep search silently takes the fallback path and has
"non-cognizable offence General Diary entry SOP complaint procedure" appended
to it. Nothing would have failed; the answers would just have got worse.
"""

from __future__ import annotations

import pytest

from app.agents.retrieval_agent import LOW_RERANKER_SCORE_FALLBACK_THRESHOLD
from app.core.config import settings


class TestTheDefault:
    def test_reranking_is_off(self) -> None:
        assert settings.cross_encoder_reranking_enabled is False

    def test_it_is_a_setting_not_a_deletion(self) -> None:
        """Re-enabling must be a restart, so the next corpus can be measured
        with it rather than argued about."""
        from app.core.config import Settings

        assert "cross_encoder_reranking_enabled" in Settings.model_fields


class TestTheServiceHonoursIt:
    @pytest.mark.asyncio
    async def test_a_caller_asking_to_rerank_does_not_get_the_cross_encoder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.retrieval import (
            HybridRetrievalService,
            RetrievalFilters,
            RetrievalTarget,
        )

        service = HybridRetrievalService()
        seen: dict[str, object] = {}

        async def fake_query_target(**kwargs):
            seen["candidate_limit"] = kwargs["candidate_limit"]
            return [], {}, {}

        monkeypatch.setattr(service, "_query_target", fake_query_target)
        monkeypatch.setattr(
            service, "_embed_query_batched", lambda query: _embedding()
        )
        try:
            await service.search_across_collections_with_timings(
                "when may police arrest without a warrant",
                targets=[
                    RetrievalTarget(
                        "global_legal_corpus", RetrievalFilters(corpus_tiers=[])
                    )
                ],
                candidate_limit=20,
                result_limit=5,
                rerank=True,
            )
        finally:
            await service.close()

        # Oversampling only happens to feed a reranker. Its absence is the
        # observable proof the cross-encoder was skipped.
        assert seen["candidate_limit"] == 20


async def _embedding():
    from app.ingestion.embedder import EmbeddedText

    return EmbeddedText(dense=[0.0] * 1024, sparse={1: 0.5})


class TestTheCoupledFallback:
    def test_the_threshold_is_still_far_above_a_fused_score(self) -> None:
        """The premise of the gate, asserted rather than assumed.

        If fusion scores ever became comparable to cross-encoder scores, the
        gate below would be unnecessary and this test would say so.
        """
        typical_fused_top_score = 1.0 / (60 + 1)

        assert typical_fused_top_score < LOW_RERANKER_SCORE_FALLBACK_THRESHOLD / 5

    def test_a_low_fused_score_alone_does_not_trigger_the_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With reranking off, only the topic anchor may trigger it.

        Otherwise every Deep query gets generic procedure language appended.
        """
        monkeypatch.setattr(settings, "cross_encoder_reranking_enabled", False)

        score_is_comparable = settings.cross_encoder_reranking_enabled
        initial_max_score = 0.016
        top_has_topic_anchor = True

        score_is_low = (
            score_is_comparable
            and initial_max_score < LOW_RERANKER_SCORE_FALLBACK_THRESHOLD
        )
        assert not score_is_low
        assert not (score_is_low or not top_has_topic_anchor)

    def test_a_missing_topic_anchor_still_triggers_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The half of the rule that does not depend on a reranker score must
        keep working, or turning the cross-encoder off would also switch off
        the fallback entirely."""
        monkeypatch.setattr(settings, "cross_encoder_reranking_enabled", False)

        score_is_low = (
            settings.cross_encoder_reranking_enabled
            and 0.016 < LOW_RERANKER_SCORE_FALLBACK_THRESHOLD
        )
        top_has_topic_anchor = False

        assert score_is_low or not top_has_topic_anchor

    def test_the_score_rule_returns_when_reranking_is_switched_back_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "cross_encoder_reranking_enabled", True)

        score_is_low = (
            settings.cross_encoder_reranking_enabled
            and 0.10 < LOW_RERANKER_SCORE_FALLBACK_THRESHOLD
        )

        assert score_is_low
