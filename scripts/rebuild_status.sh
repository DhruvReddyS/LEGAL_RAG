#!/usr/bin/env bash
# What the rebuild is doing, without touching it.
#
# Read-only on purpose: this is the command to run while a rebuild is going,
# so it must never claim a checkpoint, write a log or hold a lock.
#
# Usage:  ./scripts/rebuild_status.sh [collection]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COLLECTION="${1:-global_legal_corpus_v4}"
LEDGER="$ROOT/data/legal_kb/logs/ingestion_checkpoint.$COLLECTION.json"
LOG="$ROOT/data/legal_kb/logs/rebuild.$COLLECTION.log"
# One document per canonical content object -- the same count the pipeline
# and the supervisor use.
TOTAL="$("$ROOT/.venv-ingest/bin/python" -c "
import sys; sys.path.insert(0, '$ROOT/backend')
from pathlib import Path
from app.ingestion.metadata import load_manifest, iter_canonical_documents
print(len(list(iter_canonical_documents(load_manifest(Path('$ROOT/data/legal_kb/metadata/canonical_documents.jsonl'))))))
" 2>/dev/null || echo 0)"

echo "collection: $COLLECTION"

if pgrep -f "run_rebuild.sh $COLLECTION" >/dev/null 2>&1; then
  echo "supervisor: RUNNING"
elif pgrep -f "app.ingestion.pipeline" >/dev/null 2>&1; then
  echo "supervisor: pipeline running (supervisor not detected)"
else
  echo "supervisor: not running"
fi

# Documents completed, and how fast, read from the checkpoint ledger's own
# timestamps rather than from the wall clock, so a paused run is not counted
# as slow progress.
python3 - "$LEDGER" "$TOTAL" <<'PY'
import json, sys, time
from datetime import datetime, timezone

ledger_path, total = sys.argv[1], int(sys.argv[2] or 0)
try:
    ledger = json.load(open(ledger_path))
except Exception:
    print(f"documents: 0/{total}  (no checkpoint ledger yet)")
    raise SystemExit(0)

completed = ledger.get("completed", {})
done = len(completed)
bar_width = 34
filled = int(bar_width * done / total) if total else 0
pct = (100 * done / total) if total else 0
print(f"documents: {done}/{total}  [{'#' * filled}{'.' * (bar_width - filled)}] {pct:.1f}%")

stamps = []
for entry in completed.values():
    value = entry.get("completed_at") if isinstance(entry, dict) else None
    if not value:
        continue
    try:
        stamps.append(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        pass
if len(stamps) >= 2:
    stamps.sort()
    span = (stamps[-1] - stamps[0]).total_seconds()
    rate = (len(stamps) - 1) / span if span > 0 else 0
    last = stamps[-1]
    idle = (datetime.now(timezone.utc) - last).total_seconds()
    print(f"last document: {last.astimezone():%H:%M:%S} ({idle/60:.0f} min ago)")
    if rate > 0 and done < total:
        remaining = (total - done) / rate
        print(f"rate: {rate*3600:.0f} documents/hour   eta: {remaining/3600:.1f} h")
PY

# Points actually written, which is the thing that matters at the end.
python3 - "$COLLECTION" <<'PY'
import json, sys, urllib.request
name = sys.argv[1]
try:
    req = urllib.request.Request(
        f"http://localhost:6333/collections/{name}/points/count",
        data=json.dumps({"exact": True}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    count = json.loads(urllib.request.urlopen(req, timeout=5).read())["result"]["count"]
    print(f"points in qdrant: {count:,}")
except Exception as error:
    print(f"points in qdrant: unavailable ({type(error).__name__})")
PY

# Swap is the usual reason a rebuild crawls on this machine, and every
# measurement is supposed to record whether the machine was swapping.
if command -v sysctl >/dev/null 2>&1; then
  echo "memory: $(sysctl -n vm.swapusage 2>/dev/null || echo 'unknown')"
fi

if [ -f "$LOG" ]; then
  echo
  # A traceback ending in KeyboardInterrupt or CancelledError is someone
  # stopping the run, not the run failing -- counting those called a Ctrl-C
  # four failures.
  errors="$(awk '
    /^Traceback/ { open = 1; next }
    open && /^[A-Za-z_.]+(Error|Exception|Interrupt|Exit)/ {
      if ($0 !~ /KeyboardInterrupt|CancelledError/) n++
      open = 0
    }
    /CRITICAL|"failed_documents": [1-9]/ { n++ }
    END { print n + 0 }' "$LOG" 2>/dev/null)"
  errors="${errors:-0}"
  stops="$(grep -cE '^(KeyboardInterrupt|asyncio.exceptions.CancelledError)' "$LOG" 2>/dev/null || true)"
  oom="$(grep -c 'mps_oom_recovery' "$LOG" 2>/dev/null || true)"
  echo "log: $LOG"
  if [ "$errors" -gt 0 ]; then
    echo "  $errors real failure(s) recorded -- inspect with:"
    echo "  grep -nE 'Traceback|CRITICAL|Exception:' '$LOG' | tail -20"
  else
    echo "  no failures recorded"
  fi
  [ "${stops:-0}" -gt 0 ] && echo "  ${stops} manual stop(s) (Ctrl-C) -- harmless, the run resumes"
  if [ "${oom:-0}" -gt 0 ]; then
    echo "  ${oom} GPU out-of-memory recoveries -- close other apps; check 'ollama ps' is empty"
  fi
  echo "last 6 lines:"
  tail -6 "$LOG" | sed 's/^/  /'
else
  echo
  echo "log: not created yet ($LOG)"
fi
