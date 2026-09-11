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
REEXTRACT=0
[ "${2:-}" = "--reextract" ] && REEXTRACT=1
LEDGER="$ROOT/data/legal_kb/logs/ingestion_checkpoint.$COLLECTION.json"
LOG="$ROOT/data/legal_kb/logs/rebuild.$COLLECTION.log"
MANIFEST="$ROOT/data/legal_kb/metadata/source_manifests/documents.jsonl"
EXTRACTED="$ROOT/data/legal_kb/processed/extracted_text"
# Counted from the manifest, never hardcoded: this was pinned at 381 while the
# corpus grew to 419, so the supervisor would have called the rebuild complete
# with 38 documents still missing.
TOTAL="$(grep -c . "$MANIFEST")"
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

echo "rebuild supervisor: $COLLECTION ($TOTAL documents), log -> $LOG"

# The 14B model, both encoders and the ingestion process do not fit in 24 GB
# together; leaving the API up turns the rebuild into a swap storm.
if lsof -ti :8000 >/dev/null 2>&1; then
  echo "  stopping the API on :8000 -- ingestion and serving must not overlap"
  pkill -f "uvicorn main:app" 2>/dev/null || true
  sleep 3
  echo "  restart it after the rebuild with: ./scripts/start_local.sh"
fi

# Re-extraction is opt-in and happens once. The marginal-note fix changes how
# PDFs are read, and --rechunk reuses cached extracted text, so without this
# the rebuild would faithfully reproduce the old woven text.
if [ "$REEXTRACT" = 1 ]; then
  STASH="$EXTRACTED.superseded"
  if [ -d "$EXTRACTED" ] && [ ! -d "$STASH" ]; then
    echo "  moving cached extracted text aside -> $(basename "$STASH")"
    mv "$EXTRACTED" "$STASH"
    mkdir -p "$EXTRACTED"
  else
    echo "  extracted text already re-read in an earlier attempt, continuing"
  fi
fi

ensure_stack
echo "  ensuring collection $COLLECTION exists"
( cd "$ROOT/backend" && \
  QDRANT_GLOBAL_COLLECTION="$COLLECTION" QDRANT_URL=http://localhost:6333 \
  "$ROOT/.venv-ingest/bin/python" -m app.ingestion.init_qdrant ) >>"$LOG" 2>&1 \
  || { echo "could not create $COLLECTION -- see $LOG"; exit 1; }

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
