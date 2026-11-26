"""The verifier can run on its own model, and only when that is configured."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.orchestrator import LegalRAGWorkflow
from app.core.config import settings
from app.services.answer_cache import AnswerCache


def test_unset_the_verifier_shares_the_writer(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ollama_verification_model", None)
    workflow = LegalRAGWorkflow(SimpleNamespace())  # type: ignore[arg-type]
    assert workflow.verification_llm is workflow.llm


def test_set_the_verifier_gets_its_own_model(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ollama_verification_model", "small-checker")
    workflow = LegalRAGWorkflow(SimpleNamespace())  # type: ignore[arg-type]
    assert workflow.verification_llm is not workflow.llm
    assert workflow.verification_llm.model == "small-checker"
    assert workflow.llm.model == settings.ollama_model


def test_an_injected_model_is_used_for_both(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ollama_verification_model", "small-checker")
    injected = SimpleNamespace(model="fake")
    workflow = LegalRAGWorkflow(SimpleNamespace(), llm=injected)  # type: ignore[arg-type]
    assert workflow.verification_llm is injected


def test_a_different_verifier_is_a_different_cached_answer(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ollama_verification_model", None)
    before = AnswerCache(limit=4)._key("what is theft", "citizen")
    monkeypatch.setattr(settings, "ollama_verification_model", "small-checker")
    assert AnswerCache(limit=4)._key("what is theft", "citizen") != before
