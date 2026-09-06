"""The roll-up is where a good number can hide a bad system.

The per-question metrics are tested next door. What is tested here is the
one thing the aggregate can get wrong on its own: choosing a denominator
that makes the score rise for a reason that is not an improvement.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_answers.py"
_spec = importlib.util.spec_from_file_location("evaluate_answers", _SCRIPT)
evaluate_answers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evaluate_answers)
aggregate = evaluate_answers.aggregate


def _row(**overrides):
    row = {
        "id": "x",
        "role": "citizen",
        "expectation": "answer",
        "abstained": False,
        "abstention_correct": True,
        "published_claims": 3,
        "unsupported_claims": 0,
        "unsupported_claim_details": [],
        "currency_required": 0,
        "currency_satisfied": 0,
        "currency_correct": True,
        "currency_missing": [],
        "reading_grade": 11.0,
        "ground_coverage": 0.5,
        "grounds_missed": [],
        "latency_ms": 40_000,
    }
    row.update(overrides)
    return row


class TestGroundCoverageCannotImproveByOmission:
    def test_an_item_without_authored_grounds_does_not_raise_the_score(self) -> None:
        """Adding an unscored question must not move the number.

        If unauthored items counted as 1.0, the fastest way to raise ground
        coverage would be to add questions and not author their grounds. If
        they counted as 0.0, authoring would be punished. They must not
        count at all.
        """
        scored = aggregate([_row(ground_coverage=0.5)])["overall"]
        with_unscored = aggregate(
            [_row(ground_coverage=0.5), _row(id="y", ground_coverage=None)]
        )["overall"]

        assert scored["ground_coverage"] == with_unscored["ground_coverage"] == 0.5
        assert with_unscored["ground_coverage_items"] == 1
        assert with_unscored["items"] == 2

    def test_the_denominator_is_reported_next_to_the_score(self) -> None:
        """0.9 over two items is not the same claim as 0.9 over forty.

        Without the count beside it, a coverage number cannot be read.
        """
        metrics = aggregate([_row(), _row(id="y", ground_coverage=None)])["overall"]

        assert metrics["ground_coverage_items"] == 1


class TestUnsupportedClaimsAreSummedNotAveraged:
    def test_one_violation_in_many_clean_runs_stays_visible(self) -> None:
        """A rate would round this to zero; the rule admits no rate.

        Averaged over sixty questions a single unsupported claim reads as
        0.017 and disappears next to the other metrics. It is summed so
        that any non-zero value is legible as what it is.
        """
        rows = [_row(id=str(n)) for n in range(59)] + [_row(id="bad", unsupported_claims=1)]

        assert aggregate(rows)["overall"]["unsupported_claims_total"] == 1


class TestCurrencyIsScoredOnlyWhereItWasOwed:
    def test_items_with_no_currency_obligation_are_excluded(self) -> None:
        """Counting them would drown the failures in free passes.

        Most questions cite nothing repealed, so scoring currency across
        every item would read near 1.0 no matter how badly the repealed
        ones were handled.
        """
        rows = [
            _row(id="a", currency_required=0, currency_correct=True),
            _row(id="b", currency_required=1, currency_satisfied=0, currency_correct=False),
        ]

        metrics = aggregate(rows)["overall"]

        assert metrics["currency_items"] == 1
        assert metrics["currency_correct"] == 0.0

    def test_no_obligations_anywhere_reports_nothing_rather_than_perfect(self) -> None:
        assert aggregate([_row(currency_required=0)])["overall"]["currency_correct"] is None


class TestRolesAreKeptApart:
    def test_a_role_that_does_well_does_not_mask_one_that_does_not(self) -> None:
        rows = [
            _row(id="a", role="citizen", ground_coverage=1.0),
            _row(id="b", role="advocate", ground_coverage=0.0),
        ]

        by_role = aggregate(rows)["by_role"]

        assert by_role["citizen"]["ground_coverage"] == 1.0
        assert by_role["advocate"]["ground_coverage"] == 0.0
