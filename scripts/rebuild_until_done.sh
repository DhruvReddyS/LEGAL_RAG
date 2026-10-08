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
# Defaulted, and the default is announced. `status` with no collection used to
# silently report on global_legal_corpus_v4 while a v5 build was running, and
# printing a stale v4 ledger next to a live v5 one is how a reader concludes
# that two rebuilds are in flight.
COLLECTION="${2:-global_legal_corpus_v4}"
if [ -z "${2:-}" ] && [ "${1:-start}" != "__loop" ]; then
  printf 'no collection given; reporting on %s\n' "$COLLECTION" >&2
fi
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
    # Ask the process table, not the PID file.
    #
    # The two guards that were here both missed a real case and a second
    # keeper was started on top of a running one. `running` reads the PID
    # file, and the PID file had been deleted; the supervisor check looks for
    # run_rebuild.sh, and the supervisor was momentarily down because the
    # keeper restarts it every 20 seconds. Neither noticed the keeper itself,
    # which is the thing that must be unique. Two keepers then shared one
    # worker, the PID file pointed at the stale one, and stopping "the"
    # rebuild stopped the wrong one.
    live_keepers="$(pgrep -f "rebuild_until_done.sh __loop $COLLECTION" | tr '\n' ' ' | sed 's/ $//')"
    if [ -n "$live_keepers" ]; then
      count=$(printf '%s\n' $live_keepers | wc -l | tr -d ' ')
      if [ "$count" -gt 1 ]; then
        echo "refusing to start: $count keepers are already running for $COLLECTION (pids $live_keepers)."
        echo "that is a broken state -- stop all but one before continuing:"
        echo "  kill $live_keepers   # then ./scripts/rebuild_until_done.sh start $COLLECTION"
        exit 1
      fi
      # Repair a PID file that disagrees with reality rather than leaving a
      # stop command pointed at nothing.
      printf '%s\n' "$live_keepers" >"$PIDFILE"
      echo "already running as pid $live_keepers"
      exit 0
    fi
    if pgrep -f "run_rebuild.sh $COLLECTION" >/dev/null; then
      echo "a supervisor for $COLLECTION is already running without a keeper; stop it first or use status"; exit 1
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
    # Exactly one, or say so. `head -1` here is what wrote a stale pid into
    # the file when two keepers were running: it picked whichever the process
    # table listed first.
    started="$(pgrep -f "rebuild_until_done.sh __loop $COLLECTION" | tr '\n' ' ' | sed 's/ $//')"
    if [ -z "$started" ]; then
      echo "keeper did not start; see ${LOG#"$ROOT"/}"; exit 1
    fi
    if [ "$(printf '%s\n' $started | wc -l | tr -d ' ')" -gt 1 ]; then
      echo "started, but $(printf '%s\n' $started | wc -l | tr -d ' ') keepers are now running (pids $started)."
      echo "stop all but one: kill $started"
      exit 1
    fi
    printf '%s\n' "$started" >"$PIDFILE"
    sleep 2
    echo "keeper running as pid $(cat "$PIDFILE"); log: ${LOG#"$ROOT"/}"
    ;;
  __loop) loop ;;
  status)
    live="$(pgrep -f "rebuild_until_done.sh __loop $COLLECTION" | tr '\n' ' ' | sed 's/ $//')"
    if [ -z "$live" ]; then
      echo "keeper: not running"
    else
      n=$(printf '%s\n' $live | wc -l | tr -d ' ')
      if [ "$n" -gt 1 ]; then
        echo "keeper: $n RUNNING (pids $live) -- more than one is a broken state"
      else
        echo "keeper: running (pid $live)"
      fi
      if [ -f "$PIDFILE" ] && ! printf '%s\n' $live | grep -qx "$(cat "$PIDFILE")"; then
        echo "keeper: the pid file says $(cat "$PIDFILE"), which is not among them; repairing"
        printf '%s\n' "$live" | head -1 >"$PIDFILE"
      fi
    fi
    echo "documents: $(done_count)/$(total)"
    pgrep -f "app.ingestion.pipeline" >/dev/null && echo "worker: embedding" || echo "worker: idle"
    [ -f "$LOG" ] && tail -3 "$LOG"
    ;;
  stop)
    # Stop every keeper discovered from the process table. A stale or missing
    # PID file is the exact failure mode this script now guards against; using
    # only that file here would leave an unrecorded duplicate alive and able to
    # restart the worker immediately after `stop` reports success.
    pkill -f "rebuild_until_done.sh __loop $COLLECTION" 2>/dev/null
    rm -f "$PIDFILE"
    pkill -f "run_rebuild.sh $COLLECTION" 2>/dev/null
    pkill -f "app.ingestion.pipeline" 2>/dev/null
    echo "stopped; the ledger keeps its place, so starting again resumes"
    ;;
  *) echo "usage: $0 {start|status|stop} [collection]"; exit 2 ;;
esac
