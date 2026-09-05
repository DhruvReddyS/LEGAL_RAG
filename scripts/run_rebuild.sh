#!/usr/bin/env bash
# Drive the corpus rebuild to completion, surviving the things that keep
# stopping it.
#
# The rebuild has died three times, and never once because of the pipeline:
# a sandbox permission error on the checkpoint lock, and twice because Docker
# Desktop stopped and took Qdrant with it. On a 24 GB machine holding the 14B
# model, two encoders and the container stack, that is not a surprise.
#
# The pipeline checkpoints after every document and skips what is already
# done, so resuming costs one document rather than the run. This turns that
# property into an operator: bring the stack up, resume, repeat until the
# ledger says every document is in.
#
# Usage:  ./scripts/run_rebuild.sh [collection]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COLLECTION="${1:-global_legal_corpus_v2}"
LEDGER="$ROOT/data/legal_kb/logs/ingestion_checkpoint.$COLLECTION.json"
LOG="$ROOT/data/legal_kb/logs/rebuild.$COLLECTION.log"
TOTAL=381
MAX_ATTEMPTS=40

completed() {
  python3 -c "
import json,sys
try:
    d=json.load(open('$LEDGER'))
    print(len(d.get('completed',{})))
except Exception:
    print(0)"
}

ensure_stack() {
  if ! docker info >/dev/null 2>&1; then
    echo "  docker is down, starting it"
    open -a Docker 2>/dev/null || true
    for _ in $(seq 1 60); do
      docker info >/dev/null 2>&1 && break
      sleep 5
    done
  fi
  docker compose --env-file "$ROOT/.env" -f "$ROOT/docker/docker-compose.yml" \
    up -d --wait postgres qdrant minio >/dev/null 2>&1
}

echo "rebuild supervisor: $COLLECTION, log -> $LOG"
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  done_count="$(completed)"
  if [ "$done_count" -ge "$TOTAL" ]; then
    echo "COMPLETE: $done_count/$TOTAL documents"
    exit 0
  fi
  echo "attempt $attempt: $done_count/$TOTAL documents done"

  ensure_stack

  ( cd "$ROOT/backend" && \
    QDRANT_GLOBAL_COLLECTION="$COLLECTION" \
    QDRANT_URL=http://localhost:6333 \
    LEGAL_KB_ROOT="$ROOT/data/legal_kb" \
    HF_HUB_OFFLINE=1 \
    HF_HOME="$ROOT/data/legal_kb/cache/models" \
    "$ROOT/.venv-ingest/bin/python" -m app.ingestion.pipeline --rechunk --resume \
  ) >>"$LOG" 2>&1

  after="$(completed)"
  if [ "$after" -le "$done_count" ]; then
    # No forward progress. Retrying immediately would spin; give the machine
    # room in case this is memory pressure, which is the usual cause.
    echo "  no progress this attempt, pausing before retry"
    sleep 60
  fi
done

echo "gave up after $MAX_ATTEMPTS attempts at $(completed)/$TOTAL"
exit 1
