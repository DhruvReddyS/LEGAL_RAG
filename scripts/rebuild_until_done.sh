#!/usr/bin/env bash
# Run the corpus rebuild to completion and keep it alive without supervision.
#
# The supervisor already resumes after a crash, but it dies with the terminal
# that started it, and it stops making progress when the Mac goes to sleep.
# This detaches it from the session, holds sleep off, and restarts it if the
# whole supervisor exits before the ledger is complete.
#
#   ./scripts/rebuild_until_done.sh start [collection]
#   ./scripts/rebuild_until_done.sh status
#   ./scripts/rebuild_until_done.sh stop
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COLLECTION="${2:-global_legal_corpus_v4}"
LOG="$ROOT/data/legal_kb/logs/rebuild_forever.$COLLECTION.log"
PIDFILE="$ROOT/data/legal_kb/logs/rebuild_forever.$COLLECTION.pid"

total() {
  "$ROOT/.venv-ingest/bin/python" -c "
import sys; sys.path.insert(0, '$ROOT/backend')
from pathlib import Path
from app.ingestion.metadata import load_manifest, iter_canonical_documents
print(len(list(iter_canonical_documents(load_manifest(Path('$ROOT/data/legal_kb/metadata/canonical_documents.jsonl'))))))
" 2>/dev/null || echo 0
}

done_count() {
  python3 -c "
import json
try:
    print(len(json.load(open('$ROOT/data/legal_kb/logs/ingestion_checkpoint.$COLLECTION.json'))['completed']))
except Exception:
    print(0)"
}

running() {
  [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

loop() {
  local target attempts=0
  target="$(total)"
  echo "$(date '+%F %T')  keeper started for $COLLECTION, target $target documents" >>"$LOG"
  while :; do
    local now; now="$(done_count)"
    if [ "$now" -ge "$target" ] && [ "$target" -gt 0 ]; then
      echo "$(date '+%F %T')  COMPLETE at $now/$target" >>"$LOG"
      rm -f "$PIDFILE"
      return 0
    fi
    # Never start a second ingestion worker: two encoders on this machine is
    # what turns a slow rebuild into a swapping one.
    if pgrep -f "app.ingestion.pipeline" >/dev/null; then
      sleep 60
      continue
    fi
    attempts=$((attempts + 1))
    echo "$(date '+%F %T')  starting supervisor, attempt $attempts, at $now/$target" >>"$LOG"
    # caffeinate holds off idle and disk sleep for as long as the rebuild runs.
    caffeinate -i -s "$ROOT/scripts/run_rebuild.sh" "$COLLECTION" --reextract >>"$LOG" 2>&1
    sleep 20
  done
}

case "${1:-start}" in
  start)
    if running; then echo "already running as pid $(cat "$PIDFILE")"; exit 0; fi
    if pgrep -f "run_rebuild.sh $COLLECTION" >/dev/null; then
      echo "a supervisor for $COLLECTION is already running; stop it first or use status"; exit 1
    fi
    mkdir -p "$(dirname "$LOG")"
    # Detach into its own session, so closing the terminal, logging out, or
    # the process group that started it being killed does not take the rebuild
    # with it. macOS has no setsid binary, so Python provides one.
    nohup "$ROOT/.venv-ingest/bin/python" -c "
import os, subprocess, sys
os.setsid()
with open(sys.argv[2], 'ab', buffering=0) as log:
    subprocess.Popen([sys.argv[1], '__loop', sys.argv[3]], stdout=log, stderr=log)
" "$0" "$LOG" "$COLLECTION" >>"$LOG" 2>&1 &
    sleep 3
    pgrep -f "rebuild_until_done.sh __loop $COLLECTION" | head -1 >"$PIDFILE"
    sleep 2
    echo "keeper running as pid $(cat "$PIDFILE"); log: ${LOG#"$ROOT"/}"
    ;;
  __loop) loop ;;
  status)
    if running; then echo "keeper: running (pid $(cat "$PIDFILE"))"; else echo "keeper: not running"; fi
    echo "documents: $(done_count)/$(total)"
    pgrep -f "app.ingestion.pipeline" >/dev/null && echo "worker: embedding" || echo "worker: idle"
    [ -f "$LOG" ] && tail -3 "$LOG"
    ;;
  stop)
    if [ -f "$PIDFILE" ]; then kill "$(cat "$PIDFILE")" 2>/dev/null; rm -f "$PIDFILE"; fi
    pkill -f "run_rebuild.sh $COLLECTION" 2>/dev/null
    pkill -f "app.ingestion.pipeline" 2>/dev/null
    echo "stopped; the ledger keeps its place, so starting again resumes"
    ;;
  *) echo "usage: $0 {start|status|stop} [collection]"; exit 2 ;;
esac
