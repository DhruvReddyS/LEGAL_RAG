from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "chat_latency_benchmark.py"
SPEC = importlib.util.spec_from_file_location("chat_latency_benchmark", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_percentile_interpolates_and_handles_empty_input() -> None:
    assert MODULE.percentile([], 0.95) == 0
    assert MODULE.percentile([100], 0.95) == 100
    assert MODULE.percentile([100, 200, 300, 400], 0.5) == 250


def test_benchmark_query_set_covers_procedure_rights_contract_and_edge_case() -> None:
    rendered = " ".join(MODULE.DEFAULT_QUERIES).casefold()
    for expected in ("fir", "bail", "article 14", "contract", "dog"):
        assert expected in rendered
