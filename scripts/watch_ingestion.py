#!/usr/bin/env python3
"""Print a line every time a corpus build crosses a progress milestone.

Reads the ingestion ledger and the canonical manifest -- two small files on
disk -- so it costs the build nothing and can be left running beside it. It
never writes, never touches Qdrant and never loads a model.

Progress is measured in **pages, not documents**, because documents vary from
2 pages to 305 and a document count moves in misleading jumps. Both are shown;
the milestone fires on pages.

The ETA comes from a trailing window rather than the whole run. A cumulative
rate averages in whatever was slow at the start -- for v5 that was Ollama
holding 11.7 GB and a CPU latch that never reopened, neither of which still
applies -- so it reads pessimistically for hours after the cause is fixed.

It also reports which device the embedder is on, because that is usually the
answer when the rate drops: MPS running out of memory falls back to CPU, and
on a memory-starved host it can stay there.

Usage:
    python scripts/watch_ingestion.py
    python scripts/watch_ingestion.py --every 5 --notify
    python scripts/watch_ingestion.py --collection global_legal_corpus_v5
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "legal_kb" / "metadata" / "canonical_documents.jsonl"
LOGS = ROOT / "data" / "legal_kb" / "logs"

# Long enough to be a real sample, short enough to reflect the host as it is
# now. One hour read 2,524 pages/h while six read 2,285 on the same build.
WINDOW_HOURS = 3.0


def manifest_pages() -> dict[str, int]:
    pages: dict[str, int] = {}
    with MANIFEST.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                pages[row["canonical_document_id"]] = row.get("page_count") or 0
    return pages


def read_ledger(collection: str) -> tuple[dict, dict]:
    path = LOGS / f"ingestion_checkpoint.{collection}.json"
    for _ in range(5):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("completed", {}), data.get("failed", {})
        except (json.JSONDecodeError, FileNotFoundError):
            # The ledger is rewritten after each document; a read can land
            # mid-write. Retrying is correct; reporting zero progress is not.
            time.sleep(0.4)
    return {}, {}


def device(collection: str) -> str:
    """Which device the embedder is on, from the rebuild log's own events."""
    log = LOGS / f"rebuild.{collection}.log"
    if not log.is_file():
        return "unknown"
    try:
        tail = subprocess.run(
            ["tail", "-n", "4000", str(log)], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return "unknown"
    state = "accelerator"
    for line in tail.splitlines():
        if '"cpu_latched"' in line:
            state = "CPU (latched after repeated accelerator OOM)"
        elif '"accelerator_reprobe"' in line:
            state = "accelerator (re-probing)"
    return state


def rate_over_window(completed: dict, pages: dict, hours: float) -> float:
    cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
    done = 0
    for key, row in completed.items():
        stamp = row.get("completed_at")
        if not stamp:
            continue
        try:
            if datetime.fromisoformat(stamp).timestamp() >= cutoff:
                done += pages.get(key, 0)
        except ValueError:
            continue
    return done / hours


def next_milestone(percent: float, step: float) -> float:
    """The next milestone strictly above where the build already is.

    Strictly above, so starting a watcher at 55% reports 60% next rather than
    immediately re-announcing a milestone that was passed hours ago. The
    opening "now" line already says where it stands.
    """
    return (int(percent / step) + 1) * step


def human(hours: float) -> str:
    if hours <= 0 or hours != hours or hours > 24 * 14:
        return "unknown"
    whole = int(hours)
    minutes = int(round((hours - whole) * 60))
    if whole and minutes:
        return f"{whole} h {minutes} min"
    return f"{whole} h" if whole else f"{minutes} min"


def notify(title: str, message: str) -> None:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification {json.dumps(message)} with title {json.dumps(title)}'],
            check=False, capture_output=True, timeout=10,
        )
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--collection", default="global_legal_corpus_v5")
    parser.add_argument("--every", type=float, default=10.0,
                        help="Percentage step between reports (default 10)")
    parser.add_argument("--poll", type=int, default=60,
                        help="Seconds between checks (default 60)")
    parser.add_argument("--notify", action="store_true",
                        help="Also raise a macOS notification at each milestone")
    args = parser.parse_args()

    pages = manifest_pages()
    total_pages = sum(pages.values())
    total_docs = len(pages)

    def snapshot():
        completed, failed = read_ledger(args.collection)
        done_pages = sum(pages.get(k, 0) for k in completed)
        return completed, failed, done_pages

    completed, failed, done_pages = snapshot()
    percent = done_pages / total_pages * 100 if total_pages else 0.0

    print(f"watching {args.collection} -- reporting every {args.every:g}%")
    print(f"{total_docs:,} documents / {total_pages:,} pages")
    print()

    def report(label: str) -> None:
        completed, failed, done_pages = snapshot()
        pct = done_pages / total_pages * 100 if total_pages else 0.0
        rate = rate_over_window(completed, pages, WINDOW_HOURS)
        eta = (total_pages - done_pages) / rate if rate > 0 else float("nan")
        now = datetime.now().strftime("%H:%M")
        line = (f"[{now}] {label:>6}  {len(completed):,}/{total_docs:,} docs  "
                f"{done_pages:,}/{total_pages:,} pages  "
                f"{rate:,.0f} pages/h  ETA {human(eta)}")
        if failed:
            line += f"  FAILED {len(failed)}"
        print(line, flush=True)
        dev = device(args.collection)
        if "CPU" in dev:
            print(f"{'':16}embedding on {dev}", flush=True)
        if args.notify:
            notify(f"Corpus build {pct:.0f}%",
                   f"{len(completed):,}/{total_docs:,} documents. ETA {human(eta)}.")

    report("now")
    # Only report milestones from here, so the next one is the next multiple
    # above where the build already is.
    next_mark = next_milestone(percent, args.every)

    try:
        while True:
            time.sleep(args.poll)
            completed, failed, done_pages = snapshot()
            percent = done_pages / total_pages * 100 if total_pages else 0.0

            if percent >= next_mark:
                report(f"{next_mark:g}%")
                while percent >= next_mark:
                    next_mark += args.every

            if len(completed) + len(failed) >= total_docs:
                print()
                report("done")
                print(f"\nBuild complete: {len(completed):,} ingested, {len(failed)} failed.")
                if args.notify:
                    notify("Corpus build complete",
                           f"{len(completed):,} documents, {len(failed)} failed.")
                print("Next: ./scripts/run_corpus_gates.sh "
                      f"{args.collection} v5-cutover")
                return 0
    except KeyboardInterrupt:
        print("\nstopped watching; the build is unaffected")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
