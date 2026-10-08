#!/usr/bin/env bash
# Run every gate a corpus version must pass before it serves anyone.
#
# There are six, they were written at different times for different reasons,
# and running them by hand means running five of them and forgetting one. This
# is the order and the arguments, in one place, with the evidence written under
# a single label so a release has one set of numbers rather than six.
#
# The gates, and what each exists to catch:
#
#   payload     a manifest field that stopped reaching the index. Both
#               source_url and currency_note were silently dropped at the
#               chunker: 0 of 200 sampled points in the serving collection
#               carried a source URL, so no citation could be opened, and no
#               point carried a currency note, so an Act whose commencement
#               notification was never located produced the same generic
#               warning as a circular nobody had checked.
#   retrieval   recall@5 and citation accuracy@5. The correctness suite was
#               green through every retrieval regression this project has had.
#   answers     ground coverage, citation coverage, unsupported claims.
#   provision   whether the governing provision is reachable at all. Recall
#               can read 0.927 while the provision that answers the question
#               is absent from the top 100.
#   latency     Fast p95, Deep's non-model overhead, time to first useful
#               output, and the evidence floors beside them.
#   currency    the two individually flagged instruments cannot read as
#               settled current law.
#
# Refuses to run while an ingestion worker is alive. Every one of these is a
# measurement, and a measurement taken while the embedder and Qdrant are busy
# is not comparable to one taken idle.
#
# Usage:
#   ./scripts/run_corpus_gates.sh global_legal_corpus_v5 v5-cutover
#   ./scripts/run_corpus_gates.sh global_legal_corpus_v5 v5-cutover --record
#
# --record sets the recorded baseline for the gates that compare against one.
# Use it to establish a new contract deliberately, never to make a failure go
# away.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COLLECTION="${1:-}"
LABEL="${2:-}"
RECORD=0
[ "${3:-}" = "--record" ] && RECORD=1

PY="$ROOT/.venv-ingest/bin/python"
OUT="$ROOT/docs/evidence/gates/$LABEL"
SUMMARY="$OUT/SUMMARY.md"

if [ -z "$COLLECTION" ] || [ -z "$LABEL" ]; then
  echo "usage: $0 <collection> <label> [--record]" >&2
  exit 2
fi

if pgrep -f "app.ingestion.pipeline" >/dev/null; then
  echo "refusing to run: an ingestion worker is alive." >&2
  echo "every gate here is a measurement, and one taken while the embedder and" >&2
  echo "Qdrant are busy is not comparable to one taken idle." >&2
  echo "  ./scripts/rebuild_until_done.sh status $COLLECTION" >&2
  exit 2
fi

if [ -z "${LEGAL_RAG_BENCHMARK_PASSWORD:-}" ]; then
  echo "refusing to run: set LEGAL_RAG_BENCHMARK_PASSWORD for the latency gate." >&2
  echo "it is never written to evidence." >&2
  exit 2
fi

mkdir -p "$OUT"
FAILED=()
PASSED=()
SKIPPED=()

note() { printf '\n\033[1m%s\033[0m\n' "$*"; }

record_result() {
  local name="$1" status="$2"
  case "$status" in
    0) PASSED+=("$name") ;;
    99) SKIPPED+=("$name") ;;
    *) FAILED+=("$name (exit $status)") ;;
  esac
}

# ---------------------------------------------------------------- payload
note "1/6 payload: manifest fields that must reach the index"
"$PY" "$ROOT/scripts/check_currency_payload_gate.py" \
  --collection "$COLLECTION" --require-complete \
  2>&1 | tee "$OUT/payload.txt"
record_result payload "${PIPESTATUS[0]}"

# ------------------------------------------------------------- retrieval
note "2/6 retrieval: recall@5 and citation accuracy@5"
"$PY" "$ROOT/scripts/evaluate_retrieval.py" --collection "$COLLECTION" \
  > "$OUT/retrieval-eval.json" 2> "$OUT/retrieval-eval.log"
retrieval_eval=$?
if [ "$retrieval_eval" -eq 0 ]; then
  if [ "$RECORD" -eq 1 ]; then
    "$PY" "$ROOT/scripts/check_quality_gate.py" --result "$OUT/retrieval-eval.json" --record \
      2>&1 | tee "$OUT/retrieval-gate.txt"
  else
    "$PY" "$ROOT/scripts/check_quality_gate.py" --result "$OUT/retrieval-eval.json" \
      2>&1 | tee "$OUT/retrieval-gate.txt"
  fi
  record_result retrieval "${PIPESTATUS[0]}"
else
  echo "the evaluation itself failed; see retrieval-eval.log" | tee "$OUT/retrieval-gate.txt"
  record_result retrieval "$retrieval_eval"
fi

# --------------------------------------------------------------- answers
note "3/6 answers: ground coverage, citations, unsupported claims"
QDRANT_GLOBAL_COLLECTION="$COLLECTION" "$PY" "$ROOT/scripts/evaluate_answers.py" \
  --label "$LABEL" 2>&1 | tee "$OUT/answer-eval.log" >/dev/null
answer_eval="${PIPESTATUS[0]}"
ANSWERS="$ROOT/docs/evidence/answers-$LABEL.json"
if [ "$answer_eval" -eq 0 ] && [ -f "$ANSWERS" ]; then
  if [ "$RECORD" -eq 1 ]; then
    "$PY" "$ROOT/scripts/check_answer_gate.py" --result "$ANSWERS" --record \
      2>&1 | tee "$OUT/answer-gate.txt"
  else
    "$PY" "$ROOT/scripts/check_answer_gate.py" --result "$ANSWERS" \
      2>&1 | tee "$OUT/answer-gate.txt"
  fi
  record_result answers "${PIPESTATUS[0]}"
else
  echo "the evaluation itself failed; see answer-eval.log" | tee "$OUT/answer-gate.txt"
  record_result answers "$answer_eval"
fi

# ------------------------------------------------------------- provision
note "4/6 provision reach: can the governing provision be reached at all"
if [ "$RECORD" -eq 1 ]; then
  QDRANT_GLOBAL_COLLECTION="$COLLECTION" "$PY" "$ROOT/scripts/check_provision_reach.py" --record \
    2>&1 | tee "$OUT/provision.txt"
else
  QDRANT_GLOBAL_COLLECTION="$COLLECTION" "$PY" "$ROOT/scripts/check_provision_reach.py" \
    2>&1 | tee "$OUT/provision.txt"
fi
record_result provision "${PIPESTATUS[0]}"

# ------------------------------------------------------- retrieval health
note "5/6 retrieval health: index and configuration"
QDRANT_GLOBAL_COLLECTION="$COLLECTION" "$PY" "$ROOT/scripts/verify_retrieval_health.py" \
  --json "$OUT/retrieval-health.json" 2>&1 | tee "$OUT/health.txt"
record_result health "${PIPESTATUS[0]}"

# --------------------------------------------------------------- latency
# Last, because it needs the API up and the API must be pointed at this
# collection. Started here rather than assumed, and stopped afterwards, so the
# gate cannot silently measure whatever was already running on port 8000 --
# which on this host is a container built from the CPU torch wheel.
note "6/6 latency: Fast p95, Deep overhead, time to first useful output"
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "something already holds port 8000; stop it so this gate measures the" | tee "$OUT/latency-gate.txt"
  echo "collection under test rather than whatever is there." | tee -a "$OUT/latency-gate.txt"
  echo "  docker compose --env-file .env -f docker/docker-compose.yml stop backend" | tee -a "$OUT/latency-gate.txt"
  record_result latency 99
else
  (
    cd "$ROOT/backend" || exit 1
    QDRANT_GLOBAL_COLLECTION="$COLLECTION" nohup "$PY" -m uvicorn main:app \
      --host 127.0.0.1 --port 8000 > "$OUT/backend.log" 2>&1 &
    echo $! > "$OUT/backend.pid"
  )
  ready=0
  for _ in $(seq 1 120); do
    if curl -fsS --max-time 3 http://127.0.0.1:8000/health/ready >/dev/null 2>&1; then ready=1; break; fi
    sleep 2
  done
  if [ "$ready" -eq 1 ]; then
    curl -s http://127.0.0.1:8000/health/ready > "$OUT/health-ready.json"
    "$PY" "$ROOT/scripts/latency_benchmark.py" --label "$LABEL" --mode both --repeats 3 \
      --output "$OUT/latency.json" > "$OUT/latency-bench.log" 2>&1
    bench=$?
    if [ "$bench" -eq 0 ]; then
      if [ "$RECORD" -eq 1 ]; then
        "$PY" "$ROOT/scripts/check_latency_gate.py" --result "$OUT/latency.json" --record \
          2>&1 | tee "$OUT/latency-gate.txt"
      else
        "$PY" "$ROOT/scripts/check_latency_gate.py" --result "$OUT/latency.json" \
          2>&1 | tee "$OUT/latency-gate.txt"
      fi
      record_result latency "${PIPESTATUS[0]}"
    else
      echo "the benchmark itself failed; see latency-bench.log" | tee "$OUT/latency-gate.txt"
      record_result latency "$bench"
    fi
  else
    echo "the API did not become ready; see backend.log" | tee "$OUT/latency-gate.txt"
    record_result latency 1
  fi
  if [ -f "$OUT/backend.pid" ]; then
    kill "$(cat "$OUT/backend.pid")" 2>/dev/null
    rm -f "$OUT/backend.pid"
  fi
fi

# ---------------------------------------------------------------- summary
{
  echo "# Corpus gates: $LABEL"
  echo
  echo "Collection: \`$COLLECTION\`"
  echo "Run: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Commit: $(git -C "$ROOT" rev-parse --short HEAD)"
  [ "$RECORD" -eq 1 ] && echo "Baselines were **recorded** by this run, not compared."
  echo
  echo "| Gate | Result |"
  echo "|---|---|"
  for name in "${PASSED[@]+"${PASSED[@]}"}"; do echo "| $name | passed |"; done
  for name in "${SKIPPED[@]+"${SKIPPED[@]}"}"; do echo "| $name | skipped |"; done
  for name in "${FAILED[@]+"${FAILED[@]}"}"; do echo "| $name | **FAILED** |"; done
  echo
  echo "Per-gate output is beside this file."
} > "$SUMMARY"

note "summary"
cat "$SUMMARY"
echo
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "GATES FAILED: ${FAILED[*]}" >&2
  echo "the collection must not be promoted to serving." >&2
  exit 1
fi
if [ "${#SKIPPED[@]}" -gt 0 ]; then
  echo "gates skipped: ${SKIPPED[*]}" >&2
  echo "a skipped gate is not a passed gate; resolve it before a cutover." >&2
  exit 3
fi
echo "All gates passed for $COLLECTION."
