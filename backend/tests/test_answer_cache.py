"""A repeated question is served fast, and only when nothing it depends on changed."""

from __future__ import annotations

from unittest.mock import patch

from app.agents.orchestrator import LegalRAGWorkflow
from app.services import answer_cache
from app.services.answer_cache import AnswerCache, cacheable_request
from app.services.generation import INSUFFICIENT_EVIDENCE

PUBLISHED = {"final_answer": "An answer. [1]", "citations": [{"number": 1}], "timings": {}}


def _cache(**kwargs) -> AnswerCache:
    cache = AnswerCache(limit=kwargs.pop("limit", 4), **kwargs)
    cache._prompts = {"reasoning": "abc"}
    return cache


def test_the_same_question_is_found_whatever_its_spacing_or_case() -> None:
    cache = _cache()
    cache.put("What are my rights?", "citizen", PUBLISHED)
    assert cache.get("  what ARE my   rights? ", "citizen") == PUBLISHED


def test_roles_do_not_share_answers() -> None:
    cache = _cache()
    cache.put("What are my rights?", "citizen", PUBLISHED)
    assert cache.get("What are my rights?", "police") is None


def test_a_refusal_or_an_uncited_answer_is_never_kept() -> None:
    cache = _cache()
    cache.put("a", "citizen", {"final_answer": INSUFFICIENT_EVIDENCE, "citations": [{"number": 1}]})
    cache.put("b", "citizen", {"final_answer": "Text", "citations": []})
    assert cache.get("a", "citizen") is None
    assert cache.get("b", "citizen") is None


def test_quarantining_a_document_misses_the_old_answer() -> None:
    cache = _cache()
    cache.put("q", "citizen", PUBLISHED)
    with patch.object(answer_cache, "quarantined_document_ids", return_value=frozenset({"doc"})):
        assert cache.get("q", "citizen") is None


def test_changing_curated_currency_misses_the_old_answer() -> None:
    cache = _cache()
    cache.put("q", "citizen", PUBLISHED)
    with patch.object(answer_cache, "_currency_version", return_value=-1):
        assert cache.get("q", "citizen") is None


def test_changing_the_collection_misses_the_old_answer() -> None:
    cache = _cache()
    cache.put("q", "citizen", PUBLISHED)
    with patch.object(answer_cache.settings, "qdrant_global_collection", "another"):
        assert cache.get("q", "citizen") is None


def test_an_entry_expires() -> None:
    cache = _cache(time_to_live=-1)
    cache.put("q", "citizen", PUBLISHED)
    assert cache.get("q", "citizen") is None


def test_the_oldest_entry_makes_room() -> None:
    cache = _cache(limit=1)
    cache.put("first", "citizen", PUBLISHED)
    cache.put("second", "citizen", PUBLISHED)
    assert cache.get("first", "citizen") is None
    assert cache.get("second", "citizen") == PUBLISHED


def test_a_change_to_a_returned_answer_does_not_reach_the_cache() -> None:
    cache = _cache()
    cache.put("q", "citizen", PUBLISHED)
    cache.get("q", "citizen")["final_answer"] = "edited"
    assert cache.get("q", "citizen")["final_answer"] == PUBLISHED["final_answer"]


def test_only_a_fresh_question_qualifies() -> None:
    assert cacheable_request(case_id=None, history=[], document_context="")
    assert not cacheable_request(case_id="case", history=[], document_context="")
    assert not cacheable_request(case_id=None, history=[{"role": "user"}], document_context="")
    assert not cacheable_request(case_id=None, history=[], document_context="a document")


class _Graph:
    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, state):
        self.calls += 1
        return {**state, **PUBLISHED, "stage_metrics": []}


def _workflow() -> tuple[LegalRAGWorkflow, _Graph]:
    workflow = LegalRAGWorkflow.__new__(LegalRAGWorkflow)
    workflow.graph = _Graph()
    workflow.answer_cache = _cache()
    return workflow, workflow.graph


async def test_a_repeat_skips_the_model_and_says_it_was_reused() -> None:
    workflow, graph = _workflow()
    first = await workflow.run(query="q", role="citizen", case_id=None, history=[])
    second = await workflow.run(query="q", role="citizen", case_id=None, history=[])
    assert graph.calls == 1
    assert second["final_answer"] == first["final_answer"]
    assert second["timings"]["answer_cache_hit"] is True
    assert second["run_id"] != first["run_id"]


async def test_case_questions_and_follow_ups_always_run_in_full() -> None:
    workflow, graph = _workflow()
    await workflow.run(query="q", role="citizen", case_id="case", history=[])
    await workflow.run(query="q", role="citizen", case_id="case", history=[])
    await workflow.run(query="q", role="citizen", case_id=None, history=[{"role": "user", "content": "x"}])
    assert graph.calls == 3
