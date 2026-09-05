#!/usr/bin/env bash
# Everything that has to be measured on a quiet machine, in one pass.
#
# Run this after the v2 rebuild has finished and after a reboot, before
# reopening other applications. The order is deliberate: the two evaluations
# share a warm embedding model, and the LLM baseline runs last because it is
# the only measurement that loads the 14B and the only one whose numbers are
# destroyed by memory pressure.
#
# It refuses to start on a machine that is already swapping, because a timing
# taken under paging is not merely noisy -- it is wrong in the direction that
# makes a real improvement look like a regression.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv-ingest/bin/python"
EVID="$ROOT/docs/evidence"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
export HF_HUB_OFFLINE=1
export HF_HOME="$ROOT/data/legal_kb/cache/models"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

say "0. Preconditions"

swap_used_mb="$(sysctl -n vm.swapusage | sed -E 's/.*used = ([0-9.]+)M.*/\1/')"
printf '   swap in use: %s MB\n' "$swap_used_mb"
if (( $(printf '%.0f' "$swap_used_mb") > 2048 )); then
  echo "   REFUSING: more than 2 GB of swap is already in use."
  echo "   Reboot and run this before reopening other applications."
  echo "   Override with ALLOW_DIRTY=1 if you accept the numbers will not be comparable."
  [ "${ALLOW_DIRTY:-0}" = "1" ] || exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "   starting Docker"
  open -a Docker 2>/dev/null || true
  for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 5; done
fi
docker compose --env-file "$ROOT/.env" -f "$ROOT/docker/docker-compose.yml" \
  up -d --wait postgres qdrant minio >/dev/null 2>&1
echo "   containers up"

if ! curl -s --max-time 5 http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "   starting Ollama"
  (ollama serve >/dev/null 2>&1 &)
  for _ in $(seq 1 30); do
    curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1 && break
    sleep 2
  done
fi
echo "   ollama reachable"

# Read the ledger, and keep "the file says 0" distinct from "I could not read
# the file". Defaulting a failed read to 0 reported a confident 0/381 against a
# complete index, because macOS data protection had not settled 53 seconds
# after a reboot -- the same "Operation not permitted" that killed this
# rebuild once already. An unreadable ledger is an unknown, not a zero.
LEDGER="$ROOT/data/legal_kb/logs/ingestion_checkpoint.global_legal_corpus_v2.json"
completed=""
for attempt in 1 2 3 4 5 6; do
  if completed="$("$PY" -c "
import json
print(len(json.load(open('$LEDGER')).get('completed',{})))" 2>&1)" \
     && [[ "$completed" =~ ^[0-9]+$ ]]; then
    break
  fi
  echo "   ledger unreadable (attempt $attempt): ${completed:-no output}"
  completed=""
  sleep 10
done

if [ -z "$completed" ]; then
  echo "   REFUSING: could not read the rebuild ledger at all."
  echo "   That is not the same as an empty one. Check $LEDGER and re-run."
  exit 1
fi

printf '   v2 rebuild: %s/381 documents\n' "$completed"
if [ "$completed" -lt 381 ]; then
  echo "   REFUSING: the v2 index is incomplete, so a comparison against it would"
  echo "   measure a missing corpus rather than a different chunking strategy."
  exit 1
fi

say "1. v1 — confirms the dead-code removal changed no behaviour"
"$PY" "$ROOT/scripts/evaluate_retrieval.py" \
  --configs dense sparse hybrid reranked \
  --collection global_legal_corpus \
  --out "$EVID/eval-v1-$STAMP.json" 2>&1 | grep -viE "fetching|it/s|tokenizer"

say "2. v2 — the new chunk contract, same 48 items"
"$PY" "$ROOT/scripts/evaluate_retrieval.py" \
  --configs dense sparse hybrid reranked \
  --collection global_legal_corpus_v2 \
  --out "$EVID/eval-v2-$STAMP.json" 2>&1 | grep -viE "fetching|it/s|tokenizer"

say "3. v1 against the recorded baseline"
"$PY" "$ROOT/scripts/check_quality_gate.py" --result "$EVID/eval-v1-$STAMP.json" || true

say "4. Side by side"
"$PY" - "$EVID/eval-v1-$STAMP.json" "$EVID/eval-v2-$STAMP.json" <<'PYEOF'
import json, sys
v1, v2 = (json.load(open(p)) for p in sys.argv[1:3])
keys = ("recall_at_1","recall_at_5","recall_at_20","mrr","ndcg_at_10",
        "citation_accuracy_at_5","abstention_accuracy","false_abstention_rate")
label = {"recall_at_1":"R@1","recall_at_5":"R@5","recall_at_20":"R@20","mrr":"MRR",
         "ndcg_at_10":"nDCG@10","citation_accuracy_at_5":"cite@5",
         "abstention_accuracy":"abstain","false_abstention_rate":"false abstain"}
for config in ("hybrid","dense","sparse","reranked"):
    a = v1["configs"].get(config); b = v2["configs"].get(config)
    if not a or not b: continue
    print(f"\n  {config}")
    print(f"    {'metric':<16}{'v1':>8}{'v2':>8}{'delta':>9}")
    for k in keys:
        x, y = a["summary"].get(k), b["summary"].get(k)
        if x is None or y is None: continue
        d = y - x
        flag = "  <-- worse" if (d < -0.02 and k != "false_abstention_rate") or (d > 0.02 and k == "false_abstention_rate") else ""
        print(f"    {label[k]:<16}{x:>8.3f}{y:>8.3f}{d:>+9.3f}{flag}")
    print("    by role (R@5 / cite@5)")
    for role in sorted(a["summary"].get("by_role", {})):
        ra, rb = a["summary"]["by_role"][role], b["summary"]["by_role"].get(role, {})
        if not rb: continue
        print(f"      {role:<10} {ra['recall_at_5']:.2f} -> {rb['recall_at_5']:.2f}   "
              f"{ra['citation_accuracy_at_5']:.2f} -> {rb['citation_accuracy_at_5']:.2f}")
print("\n  Cut over only if v2 wins on recall and citation accuracy.")
print("  Not on point count, not on latency.")
PYEOF

say "5. LLM baseline (loads the 14B; runs last for that reason)"
"$PY" "$ROOT/scripts/measure_baseline.py" --out "$EVID/baseline-$STAMP.json" 2>&1 \
  | grep -viE "fetching|it/s|tokenizer"

say "Done"
echo "   docs/evidence/eval-v1-$STAMP.json"
echo "   docs/evidence/eval-v2-$STAMP.json"
echo "   docs/evidence/baseline-$STAMP.json"
