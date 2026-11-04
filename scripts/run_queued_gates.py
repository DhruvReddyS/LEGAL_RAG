#!/usr/bin/env python3
"""Execute a gate run queued from the release console.

The API cannot run the gates itself: the suite needs an idle machine, starts its
own API on port 8000 and takes hours. An operator starts this on the host, with
LEGAL_RAG_BENCHMARK_PASSWORD set, once the backend is stopped. It takes the
oldest queued run, runs scripts/run_corpus_gates.sh, and records the exit code,
which the console then shows beside the evidence the suite wrote.

    ./scripts/run_queued_gates.py --once
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.services.admin_release import (  # noqa: E402
    COLLECTION_RE,
    LABEL_RE,
    claim_next_gate_run,
    finish_gate_run,
)

SCRIPT = ROOT / "scripts" / "run_corpus_gates.sh"


async def run_next(script: Path = SCRIPT) -> tuple[str, int] | None:
    async with AsyncSessionLocal() as session:
        run = await claim_next_gate_run(session)
        if run is None:
            return None
        run_id, label, collection = run.id, run.label, run.collection
    # Checked again here: this value becomes a process argument on the host.
    if not LABEL_RE.fullmatch(label) or not COLLECTION_RE.fullmatch(collection):
        exit_code = 2
    else:
        completed = await asyncio.to_thread(
            subprocess.run, [str(script), collection, label], check=False
        )
        exit_code = completed.returncode
    async with AsyncSessionLocal() as session:
        await finish_gate_run(session, run_id, exit_code)
    return label, exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", required=True, help="Run one queued run and exit")
    parser.parse_args()
    outcome = asyncio.run(run_next())
    if outcome is None:
        print("no gate run is queued")
        return 0
    label, exit_code = outcome
    print(f"gate run {label} finished with exit code {exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
