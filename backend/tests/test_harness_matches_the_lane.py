"""The evaluation harness must measure the system that actually runs.

Four times now the harness has described a configuration production does not
use, and every one made the recorded numbers wrong in a way no test caught:

  1. it applied only the coverage floor, crediting the mandatory-term
     requirement with nothing, while its docstring claimed to measure deployed
     behaviour;
  2. it scored citation accuracy over the raw retrieved list, a third of whose
     slots repeat a document the reader has already been shown;
  3. a first attempt to fix that reimplemented the document dedup without the
     coverage gate;
  4. it retrieved 20 candidates and scored 5 slots, where the lane retrieves 8
     and shows 4 -- which alone moved police citation accuracy from 0.44 to
     0.57.

A number measured against a system nobody runs is worse than no number,
because it gets quoted. These assert the two cannot drift apart again.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts" / "evaluate_retrieval.py"


@pytest.fixture(scope="module")
def harness_source() -> str:
    if not HARNESS.is_file():
        pytest.skip("evaluation harness is not present in this checkout")
    return HARNESS.read_text(encoding="utf-8")


def test_the_harness_uses_the_lane_selection_rather_than_its_own(harness_source: str) -> None:
    """`publishable_hits` is the lane's gate. Reimplementing it is how three of
    the four drifts happened."""
    assert "publishable_hits" in harness_source
    assert "_select_diverse_hits" in harness_source


def test_it_takes_the_result_limit_from_settings(harness_source: str) -> None:
    """Not a literal. `fast_result_limit` is 4 and the harness scored 5."""
    assert "settings.fast_result_limit" in harness_source
    assert "settings.fast_candidate_limit" in harness_source


def test_no_hardcoded_slot_count_survives(harness_source: str) -> None:
    tree = ast.parse(harness_source)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None)
        if name not in {"precision_at"}:
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, int):
                offenders.append(f"line {node.lineno}: precision_at({argument.value})")
    assert not offenders, (
        "citation accuracy must be scored over the lane's result limit, not a "
        f"literal: {offenders}"
    )


def test_the_lane_still_narrows_before_showing() -> None:
    """The property the harness is mirroring.

    If the lane stopped narrowing -- candidate limit equal to result limit --
    the harness would faithfully measure that, and the guard above would keep
    passing while both were wrong together. So the shape is asserted here too.
    """
    from app.core.config import settings

    assert settings.fast_candidate_limit > settings.fast_result_limit, (
        "the lane retrieves more candidates than it shows; if that stops being "
        "true, the selection step is doing nothing"
    )
