"""A measurement has to record how the text was generated.

The standing rule is that every measurement records prompt version, model
version, temperature and seed. The harness satisfied that on paper: it read
settings.ollama_temperature and settings.ollama_seed with a None default.
Neither attribute exists. Every recorded run therefore said temperature:
null, seed: null -- which reads as "not measured" and is indistinguishable
from a harness that never tried.

That failure is silent by construction, because getattr with a default
cannot raise. These tests make it loud.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from app.services.llm import SEED, TEMPERATURE, sampling_settings

ROOT = Path(__file__).resolve().parents[2]
LLM_SOURCE = (ROOT / "backend/app/services/llm.py").read_text(encoding="utf-8")


def test_the_recorded_settings_are_populated_not_null() -> None:
    recorded = sampling_settings()

    assert recorded["temperature"] is not None
    assert "seed" in recorded
    # "no seed" is a fact worth recording; a null that means "unread" is not
    # distinguishable from it without this flag.
    assert recorded["seeded"] is (SEED is not None)


def test_every_request_sends_the_temperature_that_is_recorded() -> None:
    """Recording 0.0 while sending 0.7 somewhere would be worse than
    recording nothing, because it would look authoritative.

    Asserted against the source rather than by calling the client, which
    would need a running Ollama; what matters is that no literal survives
    beside the shared constant.
    """
    literals = re.findall(r'"temperature":\s*([^,\n]+)', LLM_SOURCE)

    assert literals, "no temperature is sent at all"
    for literal in literals:
        assert literal.strip() == "TEMPERATURE", (
            f'a request sends temperature {literal.strip()} directly. Every '
            "call site must use the shared constant, or a measurement records "
            "one value while another is used."
        )


def test_the_declared_decoding_matches_the_temperature() -> None:
    recorded = sampling_settings()

    assert recorded["decoding"] == ("greedy" if TEMPERATURE == 0.0 else "sampled")


def test_the_harness_records_them_in_its_measurement_config() -> None:
    """The field has to reach the file, not merely exist in a helper."""
    spec = importlib.util.spec_from_file_location(
        "evaluate_answers", ROOT / "scripts" / "evaluate_answers.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = (ROOT / "scripts" / "evaluate_answers.py").read_text(encoding="utf-8")

    assert "sampling_settings()" in source, (
        "the harness no longer reads the generator's own sampling settings; "
        "anything else it reads can silently be absent"
    )
    assert "getattr(settings" not in source, (
        "getattr with a default cannot raise, so a renamed or missing setting "
        "records null instead of failing. That is the bug this file exists for."
    )
