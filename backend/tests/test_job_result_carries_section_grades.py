"""An escalated Deep answer must show the same grades a sync Deep answer does."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.job_worker import DurableJobWorker


def _result(**extra) -> dict:
    return {
        "final_answer": "answer",
        "citations": [],
        "confidence_score": 0.9,
        "evidence_strength": "strong",
        "intent": SimpleNamespace(model_dump=lambda mode: {"intent": "x"}),
        "agent_trace": [],
        **extra,
    }


def test_the_grades_reach_the_job_result():
    grades = [{"section": "Basis", "confidence": "strong", "reason": "two sources"}]
    serialized = DurableJobWorker._serialize_result(_result(section_confidence=grades), {"chat_session_id": "s"})
    assert serialized["section_confidence"] == grades


def test_a_result_with_no_grades_serialises_to_an_empty_list():
    serialized = DurableJobWorker._serialize_result(_result(), {"chat_session_id": "s"})
    assert serialized["section_confidence"] == []
