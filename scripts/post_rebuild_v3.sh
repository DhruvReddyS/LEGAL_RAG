#!/usr/bin/env bash
# Everything to be measured once the v3 rebuild finishes, in the one order
# that produces comparable numbers.
#
# Step 2 is why this script exists. The last comparison in this project
# reported a v2 regression -- R@1 falling 0.667 to 0.619 -- that was not
# real: v1 had been through the currency migration and v2 had not, so the
# supersession guards read false for every point in v2 and the two indexes
# were answering different questions. Running the migration first closed the
# gap entirely, to 0.670. A rebuilt collection is not comparable until its
# currency payload is resolved, and forgetting that step is invisible in
# every number the run prints.
#
# Refuses to start on a machine that is already swapping. A timing taken
# under paging is not merely noisy; it is wrong in the direction that makes
# a real improvement look like a regression.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv-ingest/bin/python"
EVID="$ROOT/docs/evidence"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OLD="${OLD_COLLECTION:-global_legal_corpus_v2}"
NEW="${NEW_COLLECTION:-global_legal_corpus_v3}"
export HF_HUB_OFFLINE=1
export HF_HOME="$ROOT/data/legal_kb/cache/models"
export LEGAL_KB_ROOT="$ROOT/data/legal_kb"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\n   REFUSING: %s\n' "$*"; exit 1; }

say "0. Preconditions"

# Pageouts, not the swap-used counter. "Used" grows and never shrinks on
# macOS, so it reports 15 GB on a machine doing no paging at all -- which it
# did during this session, and which would have refused this run for no
# reason. What matters is whether pages are being written out now.
before_pageouts="$(vm_stat | awk '/Pageouts/{gsub(/\./,"");print $NF}')"
sleep 10
after_pageouts="$(vm_stat | awk '/Pageouts/{gsub(/\./,"");print $NF}')"
pageout_rate=$(( after_pageouts - before_pageouts ))
printf '   pageouts over 10s: %s\n' "$pageout_rate"
if [ "$pageout_rate" -gt 2000 ]; then
  echo "   The machine is actively paging."
  echo "   Reboot and run this before reopening other applications."
  echo "   Override with ALLOW_DIRTY=1 if you accept the numbers are not comparable."
  [ "${ALLOW_DIRTY:-0}" = "1" ] || exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "   starting Docker"
  open -a Docker 2>/dev/null || true
  for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 5; done
fi
docker compose --env-file "$ROOT/.env" -f "$ROOT/docker/docker-compose.yml" \
  up -d --wait postgres qdrant minio >/dev/null 2>&1 || die "containers did not come up"
echo "   containers up"

if ! curl -s --max-time 5 http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "   starting Ollama"
  (ollama serve >/dev/null 2>&1 &)
  for _ in $(seq 1 30); do
    curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1 && break
    sleep 2
  done
fi
curl -s --max-time 5 http://localhost:11434/api/tags >/dev/null 2>&1 \
  || die "Ollama is not reachable"
echo "   ollama reachable"

# An unreadable ledger is an unknown, not a zero. Defaulting a failed read to
# 0 once reported a confident 0/381 against a complete index, because macOS
# data protection had not settled after a reboot.
LEDGER="$ROOT/data/legal_kb/logs/ingestion_checkpoint.$NEW.json"
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
[ -n "$completed" ] || die "could not read $LEDGER at all. That is not an empty ledger."

printf '   %s rebuild: %s/381 documents\n' "$NEW" "$completed"
[ "$completed" -ge 381 ] || die "$NEW is incomplete; a comparison would measure a missing corpus rather than a better parser."

say "1. Resolve currency on $NEW  (the step whose absence faked a regression)"
"$PY" "$ROOT/scripts/migrate_currency_payload.py" --collection "$NEW" 2>&1 \
  | grep -viE "fetching|it/s|tokenizer" || die "currency migration failed"

say "2. Retrieval — $OLD"
"$PY" "$ROOT/scripts/evaluate_retrieval.py" --configs hybrid \
  --collection "$OLD" --out "$EVID/eval-$OLD-$STAMP.json" 2>&1 \
  | grep -viE "fetching|it/s|tokenizer"

say "3. Retrieval — $NEW"
"$PY" "$ROOT/scripts/evaluate_retrieval.py" --configs hybrid \
  --collection "$NEW" --out "$EVID/eval-$NEW-$STAMP.json" 2>&1 \
  | grep -viE "fetching|it/s|tokenizer"

say "4. Retrieval, side by side"
"$PY" - "$EVID/eval-$OLD-$STAMP.json" "$EVID/eval-$NEW-$STAMP.json" <<'PYEOF'
import json, sys
old, new = (json.load(open(p)) for p in sys.argv[1:3])
keys = ("recall_at_1","recall_at_5","recall_at_20","mrr","ndcg_at_10",
        "citation_accuracy_at_5","abstention_accuracy","false_abstention_rate")
a, b = old["configs"]["hybrid"]["summary"], new["configs"]["hybrid"]["summary"]
print(f"    {'metric':<24}{'v2':>8}{'v3':>8}{'delta':>9}")
for k in keys:
    x, y = a.get(k), b.get(k)
    if x is None or y is None: continue
    d = y - x
    worse = (d < -0.02 and k != "false_abstention_rate") or (d > 0.02 and k == "false_abstention_rate")
    print(f"    {k:<24}{x:>8.3f}{y:>8.3f}{d:>+9.3f}{'  <-- worse' if worse else ''}")
print("\n    by role (R@5 / cite@5)")
for role in sorted(a.get("by_role", {})):
    ra, rb = a["by_role"][role], b.get("by_role", {}).get(role, {})
    if not rb: continue
    print(f"      {role:<10} {ra['recall_at_5']:.2f} -> {rb['recall_at_5']:.2f}   "
          f"{ra['citation_accuracy_at_5']:.2f} -> {rb['citation_accuracy_at_5']:.2f}")
PYEOF

say "5. Answer quality on $NEW  (loads the 14B; runs last for that reason)"
# stdbuf, because grep block-buffers when its stdout is a file rather than a
# terminal. Without it the per-question progress lines sat in grep's buffer
# for three and a half hours and neither the operator nor I could tell a slow
# run from a stuck one.
QDRANT_GLOBAL_COLLECTION="$NEW" stdbuf -oL -eL "$PY" "$ROOT/scripts/evaluate_answers.py" --label "$NEW-$STAMP" 2>&1 \
  | stdbuf -oL grep -viE "fetching|it/s|tokenizer"

say "Done — nothing has been recorded as a baseline"
cat <<TXT
   Read the numbers first. Record only what you mean to defend:

     python scripts/check_quality_gate.py --result $EVID/eval-$NEW-$STAMP.json --record
     python scripts/check_answer_gate.py  --result $EVID/answers-$NEW-$STAMP.json --record

   Cut the application over to $NEW only if it wins on recall and citation
   accuracy. Not on point count, not on latency.
TXT
