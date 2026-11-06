#!/usr/bin/env bash
# Run Ollama without llama-server's 8 GB prompt cache (--cache-ram, default 8192 MiB).
#
# Corpusil makes one request at a time on one slot, and the prompts share almost no prefix,
# so the cache held 7.9 GB for little use: the server reached 19 GB beside a 10.9 GB model,
# on a 24 GB machine, and pushed the API and its embedder into swap.
#
# Started from here rather than through launchctl, so no system setting changes. Reopening
# the Ollama app later returns everything to how it was. The app is stopped if it is running
# without this setting, since it holds the port.
set -uo pipefail

export LLAMA_ARG_CACHE_RAM=0
export OLLAMA_MODELS="${CORPUSIL_OLLAMA_MODELS:-$HOME/.ollama/models}"
BIN=/Applications/Ollama.app/Contents/Resources/ollama
[ -x "$BIN" ] || BIN="$(command -v ollama)" || { echo "ollama is not installed" >&2; exit 1; }
LOG="${TMPDIR:-/tmp}/corpusil-ollama.log"

running="$(pgrep -f 'ollama serve' | head -1)"
if [ -n "$running" ] && ps eww -p "$running" 2>/dev/null | grep -q 'LLAMA_ARG_CACHE_RAM=0'; then
  exit 0
fi
pkill -f 'Ollama.app/Contents' 2>/dev/null
pkill -f 'ollama serve' 2>/dev/null
sleep 2
nohup "$BIN" serve >"$LOG" 2>&1 &
for _ in $(seq 1 30); do
  curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && exit 0
  sleep 1
done
echo "Ollama did not start: see $LOG" >&2
exit 1
