"""The gate has to fail for the right reasons, and pass for none of the wrong ones.

A gate is only worth having if it cannot be walked around. Each test here is
a way this one could be made green without the system getting better.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_answer_gate.py"


def _report(**overrides) -> dict:
    metrics = {
        "abstention_correct": 1.0,
        "unsupported_claims_total": 0,
        "ground_coverage": 0.80,
        "ground_coverage_items": 10,
        "currency_correct": 1.0,
        "reading_grade_mean": 11.0,
        "latency_p50_s": 40.0,
    }
    metrics.update(overrides.pop("metrics", {}))
    report = {
        "golden_set": "golden_set_v3.json",
        "measurement_config": {"collection": "c"},
        "metrics": {"overall": metrics, "by_role": {}},
        "rows": [],
    }
    report.update(overrides)
    return report


def _run(tmp_path: Path, report: dict, *args: str) -> subprocess.CompletedProcess:
    result_path = tmp_path / "answers.json"
    result_path.write_text(json.dumps(report), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--result", str(result_path),
         "--baseline", str(tmp_path / "baseline.json"), *args],
        capture_output=True, text=True,
    )


def _with_baseline(tmp_path: Path, baseline: dict, current: dict) -> subprocess.CompletedProcess:
    _run(tmp_path, baseline, "--record")
    return _run(tmp_path, current)


class TestUnsupportedClaimsAreARuleNotAMetric:
    def test_a_single_violation_fails_even_with_no_baseline(self, tmp_path: Path) -> None:
        report = _report(
            metrics={"unsupported_claims_total": 1},
            rows=[{"id": "arrest-grounds", "unsupported_claim_details": ["ghost: a claim"]}],
        )

        result = _run(tmp_path, report)

        assert result.returncode == 1
        assert "UNSUPPORTED CLAIMS" in result.stderr
        assert "arrest-grounds" in result.stderr

    def test_it_cannot_be_laundered_into_a_baseline(self, tmp_path: Path) -> None:
        """--record must not accept a violation.

        Recording it would make the violation the accepted state of the
        system, and the next one would be "no change" and merge clean. This
        is the single most important property of this gate.
        """
        report = _report(
            metrics={"unsupported_claims_total": 1},
            rows=[{"id": "x", "unsupported_claim_details": ["ghost: a claim"]}],
        )

        result = _run(tmp_path, report, "--record")

        assert result.returncode == 1
        assert not (tmp_path / "baseline.json").exists()

    def test_a_wide_tolerance_does_not_reach_it(self, tmp_path: Path) -> None:
        """The rule takes no tolerance, however generous the flag."""
        report = _report(
            metrics={"unsupported_claims_total": 1},
            rows=[{"id": "x", "unsupported_claim_details": ["ghost: a claim"]}],
        )

        result = _run(tmp_path, report, "--tolerance", "1.0")

        assert result.returncode == 1

    def test_zero_violations_passes(self, tmp_path: Path) -> None:
        assert _run(tmp_path, _report(), "--record").returncode == 0


class TestRegressionsFail:
    def test_a_ground_coverage_drop_past_tolerance_fails(self, tmp_path: Path) -> None:
        """The 0.67 -> 0.50 prompt regression this project actually had.

        Retrieval was untouched, so the retrieval gate stayed green through
        the whole thing.
        """
        result = _with_baseline(
            tmp_path,
            _report(metrics={"ground_coverage": 0.67}),
            _report(metrics={"ground_coverage": 0.50}),
        )

        assert result.returncode == 1
        assert "REGRESSION" in result.stdout

    def test_noise_within_tolerance_passes(self, tmp_path: Path) -> None:
        """Generation is sampled; a zero-tolerance gate here fails on the
        same input twice and gets switched off within a week."""
        result = _with_baseline(
            tmp_path,
            _report(metrics={"ground_coverage": 0.80}),
            _report(metrics={"ground_coverage": 0.77}),
        )

        assert result.returncode == 0

    def test_an_improvement_passes(self, tmp_path: Path) -> None:
        result = _with_baseline(
            tmp_path,
            _report(metrics={"ground_coverage": 0.60}),
            _report(metrics={"ground_coverage": 0.85}),
        )

        assert result.returncode == 0

    def test_abstention_correctness_is_gated_too(self, tmp_path: Path) -> None:
        """Otherwise the cheapest way to raise ground coverage is to stop
        abstaining on the questions the corpus cannot answer."""
        result = _with_baseline(
            tmp_path,
            _report(metrics={"abstention_correct": 1.0}),
            _report(metrics={"abstention_correct": 0.8}),
        )

        assert result.returncode == 1


class TestTheDenominatorIsWatched:
    def test_scoring_fewer_items_is_reported(self, tmp_path: Path) -> None:
        """Dropping the hard questions raises the average.

        That reads as an improvement and is the opposite of one, so the
        change in the number of scored items is surfaced next to the score.
        """
        result = _with_baseline(
            tmp_path,
            _report(metrics={"ground_coverage": 0.80, "ground_coverage_items": 10}),
            _report(metrics={"ground_coverage": 0.95, "ground_coverage_items": 3}),
        )

        assert "was 10" in result.stderr

    def test_a_different_golden_set_is_reported(self, tmp_path: Path) -> None:
        baseline = _report()
        current = _report()
        current["golden_set"] = "golden_set_v4.json"

        result = _with_baseline(tmp_path, baseline, current)

        assert "different yardsticks" in result.stderr.lower()


class TestUnmeasuredMetricsDoNotSilentlyPass:
    def test_a_metric_missing_on_one_side_is_reported_not_scored(self, tmp_path: Path) -> None:
        """None is not zero and not equal.

        Treating an unmeasured metric as a pass is how a gate keeps
        reporting green after the thing it measures stops being computed.
        """
        result = _with_baseline(
            tmp_path,
            _report(metrics={"currency_correct": 1.0}),
            _report(metrics={"currency_correct": None}),
        )

        assert "not measured on both sides" in result.stdout
