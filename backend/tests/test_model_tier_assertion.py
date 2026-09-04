"""The generation model is also the judge, so its size is a safety property.

One model performs reasoning, claim verification and response generation. A
weaker model in that role does not fail visibly: it approves claims it should
have refused, which raises the verification score while making the answers
less trustworthy. So the PRD requires this at boot rather than by convention.

The temptation it guards is a real and plausible one. This machine has
qwen3:4b installed, it decodes about three times faster than the 14B, and
pointing OLLAMA_MODEL at it looks like a latency win.
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.health import (
    ALLOW_SMALL_MODEL_ENV,
    assert_reasoning_model_tier,
    is_small_tier_model,
)


class TestSizeDetection:
    @pytest.mark.parametrize(
        "model",
        ["qwen3:4b", "llama3.2:1b", "phi3:3.8b", "qwen3:0.5b", "mistral:7b"],
    )
    def test_a_small_model_is_recognised(self, model: str) -> None:
        assert is_small_tier_model(model), model

    @pytest.mark.parametrize(
        "model",
        [
            "qwen3-14b-16k:latest",
            "qwen3:14b",
            "qwen2.5:14b-instruct-q4_K_M",
            "gpt-oss:20b",
            "gpt-oss-20b-32k:latest",
        ],
    )
    def test_the_deployed_tiers_are_accepted(self, model: str) -> None:
        assert not is_small_tier_model(model), model

    def test_a_context_suffix_is_not_read_as_a_size(self) -> None:
        """"qwen3-14b-16k" carries two numbers and only one is parameters."""
        assert not is_small_tier_model("qwen3-14b-16k:latest")

    def test_an_unlabelled_model_is_not_assumed_small(self) -> None:
        """Guessing from an unlabelled name would block legitimate models.

        This exists to catch a deliberate swap, not to police naming.
        """
        assert not is_small_tier_model("some-internal-build:latest")


class TestTheBootAssertion:
    def test_it_refuses_a_small_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen3:4b")
        monkeypatch.delenv(ALLOW_SMALL_MODEL_ENV, raising=False)

        with pytest.raises(RuntimeError) as error:
            assert_reasoning_model_tier()

        assert "qwen3:4b" in str(error.value)
        assert ALLOW_SMALL_MODEL_ENV in str(error.value)

    def test_it_allows_the_configured_model(self) -> None:
        """The deployed configuration must boot."""
        assert_reasoning_model_tier()

    def test_the_override_is_explicit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen3:4b")
        monkeypatch.setenv(ALLOW_SMALL_MODEL_ENV, "1")

        assert_reasoning_model_tier() is None

    def test_the_override_does_not_fire_on_any_truthy_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A safety override should take one exact value, not anything set."""
        monkeypatch.setattr(settings, "ollama_model", "qwen3:4b")
        monkeypatch.setenv(ALLOW_SMALL_MODEL_ENV, "false")

        with pytest.raises(RuntimeError):
            assert_reasoning_model_tier()
