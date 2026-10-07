"""Premise truncation must be observable.

The verifier sees at most MAX_PREMISE_CHARACTERS of a chunk. A claim grounded
only in text beyond that is reported unsupported, which costs a retry and can
end in an abstention. The cap is a deliberate cost control; its invisibility
was not. These tests pin the behaviour, so the cap can be tuned against
evidence rather than argued about.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.verification_agent import MAX_PREMISE_CHARACTERS, build_premises


def chunk(chunk_id: str, text: str) -> SimpleNamespace:
    return SimpleNamespace(payload={"chunk_id": chunk_id, "text": text})


class TestTheCapIsApplied:
    def test_long_text_is_cut_to_the_cap(self):
        premises, _ = build_premises([chunk("a", "x" * (MAX_PREMISE_CHARACTERS + 500))])
        assert len(premises["a"]) == MAX_PREMISE_CHARACTERS

    def test_short_text_is_untouched(self):
        premises, _ = build_premises([chunk("a", "a short provision")])
        assert premises["a"] == "a short provision"


class TestTruncationIsCounted:
    def test_text_that_loses_characters_is_counted(self):
        _, truncated = build_premises([chunk("a", "x" * (MAX_PREMISE_CHARACTERS + 1))])
        assert truncated == 1

    def test_text_exactly_at_the_cap_loses_nothing_and_is_not_counted(self):
        _, truncated = build_premises([chunk("a", "x" * MAX_PREMISE_CHARACTERS)])
        assert truncated == 0

    def test_short_text_is_not_counted(self):
        _, truncated = build_premises([chunk("a", "short")])
        assert truncated == 0

    def test_only_the_oversized_chunks_are_counted(self):
        _, truncated = build_premises(
            [
                chunk("a", "x" * (MAX_PREMISE_CHARACTERS + 10)),
                chunk("b", "x" * MAX_PREMISE_CHARACTERS),
                chunk("c", "short"),
                chunk("d", "y" * (MAX_PREMISE_CHARACTERS * 2)),
            ]
        )
        assert truncated == 2

    def test_missing_text_is_not_an_error(self):
        premises, truncated = build_premises([SimpleNamespace(payload={"chunk_id": "a"})])
        assert premises == {"a": ""} and truncated == 0


def test_the_count_reaches_the_telemetry():
    import inspect

    from app.agents import verification_agent

    source = inspect.getsource(verification_agent.verification_node)
    assert '"truncated_premise_count": truncated_premise_count' in source
