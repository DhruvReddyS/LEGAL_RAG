"""Post-build writes and measurements must not race the rebuild keeper.

The keeper has brief intervals where no ``app.ingestion.pipeline`` process is
alive before it starts the next worker. Checking for the Python worker alone
therefore creates a window in which a destructive payload operation or a gate
run can begin while the keeper is about to resume ingestion.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).parents[2]


def _load(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "module_name", ["backfill_manifest_payload", "prune_reclassified_noise"]
)
@pytest.mark.parametrize(
    "active_pattern",
    [
        "app.ingestion.pipeline",
        "rebuild_until_done.sh __loop",
        "scripts/run_rebuild.sh",
    ],
)
def test_python_postbuild_tools_block_every_rebuild_phase(
    monkeypatch: pytest.MonkeyPatch, module_name: str, active_pattern: str
) -> None:
    module = _load(module_name)

    class Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(command, **_kwargs):
        return Result(0 if command[-1] == active_pattern else 1)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module.corpus_build_running() is True


@pytest.mark.parametrize(
    "module_name", ["backfill_manifest_payload", "prune_reclassified_noise"]
)
def test_python_postbuild_tools_allow_a_fully_idle_host(
    monkeypatch: pytest.MonkeyPatch, module_name: str
) -> None:
    module = _load(module_name)

    class Result:
        returncode = 1

    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: Result())
    assert module.corpus_build_running() is False


def test_gate_orchestrator_checks_the_same_three_process_phases() -> None:
    source = (ROOT / "scripts" / "run_corpus_gates.sh").read_text()
    assert 'pgrep -f "app.ingestion.pipeline"' in source
    assert 'pgrep -f "rebuild_until_done.sh __loop"' in source
    assert 'pgrep -f "scripts/run_rebuild.sh"' in source
