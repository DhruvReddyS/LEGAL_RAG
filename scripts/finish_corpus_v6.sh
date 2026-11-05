#!/usr/bin/env bash
# Everything left once the v6 rebuild has finished, safe to run again.
#
# Adds the recovered Acts, proves the clean copies parse, retires the old copies
# they replace, builds golden set v4 and runs every gate. It never switches the
# serving collection: a person reads the gate results first.
#
#   export LEGAL_RAG_BENCHMARK_PASSWORD='...'   # needed by the latency gate
#   ./scripts/finish_corpus_v6.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
COLLECTION="global_legal_corpus_v6"
PY="$ROOT/.venv-ingest/bin/python"
LEDGER="data/legal_kb/logs/ingestion_checkpoint.$COLLECTION.json"
export QDRANT_URL="http://localhost:6333"
export LEGAL_KB_ROOT="$ROOT/data/legal_kb"
export HF_HUB_OFFLINE=1
export HF_HOME="$ROOT/data/legal_kb/cache/models"

# Replaced by the clean copies in data/source_materials/missing_acts_2026-11-04.json.
OLD_COPIES=(
  gold-canonical-29627f9717f1e47f6d79ab78    # POCSO Act, scanned
  exp-canonical-0b305c1ed9b5372e7d71df88     # POCSO Act, duplicate
  civil-canonical-abe091d5a22cf2a41659f224   # POSH Act, scanned
  gold-canonical-f3f51b20a1176786db2ea744    # SC/ST Act, scanned
  exp-canonical-48399d923db97e5f74b73e53     # IT Act, as introduced
  gold-canonical-4e0dd7be87cebd3e5f8cb966    # IT Act, before the 2008 amendment
)

stop() { echo "STOPPED: $1"; exit 1; }

pgrep -f "app.ingestion.pipeline" >/dev/null && stop "the rebuild is still running."
[ -n "${LEGAL_RAG_BENCHMARK_PASSWORD:-}" ] || stop "set LEGAL_RAG_BENCHMARK_PASSWORD first."
docker info >/dev/null 2>&1 || stop "start Docker first."
docker compose --env-file .env -f docker/docker-compose.yml up -d --wait postgres qdrant minio >/dev/null 2>&1 \
  || stop "the corpus stack did not start."

echo "== 1/5 add the recovered Acts"
"$PY" scripts/update_corpus_manifest_2026_11.py || stop "manifest update failed."
"$PY" scripts/corpus_lifecycle.py add --collection "$COLLECTION" --pending || stop "adding documents failed."

echo "== 2/5 check the clean copies parse"
"$PY" scripts/check_section_coverage.py || stop "section coverage failed; old copies were kept."

echo "== 3/5 retire the old copies"
for document in "${OLD_COPIES[@]}"; do
  if grep -q "\"$document\"" "$LEDGER"; then
    "$PY" scripts/corpus_lifecycle.py retire --collection "$COLLECTION" --yes --document-id "$document" \
      || stop "retiring $document failed."
  fi
done

echo "== 4/5 build golden set v4"
"$PY" scripts/build_golden_set_v4.py || stop "golden set items did not verify; none were changed."

echo "== 5/5 run the gates (about two hours)"
./scripts/run_corpus_gates.sh "$COLLECTION" v6-cutover
result=$?

cat <<EOF

Evidence: docs/evidence/gates/v6-cutover/
Gates exit code: $result. Baselines predate golden set v4, so read each result
before recording a new baseline with that gate's own --record.

To serve v6 once satisfied, set QDRANT_GLOBAL_COLLECTION=$COLLECTION in .env and
restart. v4 and v5 stay in place for rollback.
EOF
exit "$result"
