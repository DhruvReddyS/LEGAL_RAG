#!/usr/bin/env bash
# Start Corpusil for a live demonstration on this machine.
#
# start_local.sh runs the API in Docker, whose image has CPU torch, and the frontend
# in development mode. Both are slow on a stage. This runs the API natively so it uses
# the GPU, and serves the production build of the frontend. The stores stay in Docker.
#
#   ./scripts/start_demo.sh            start, and stop everything with Ctrl+C
#   ./scripts/start_demo.sh --seed     also load demo cases and warm the demo questions
#
# The demo accounts need DEMO_PASSWORD set; see scripts/seed_demo.py.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
PY="$ROOT/.venv-ingest/bin/python"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
LOGS="${TMPDIR:-/tmp}/corpusil-demo"
mkdir -p "$LOGS"

fail() { printf 'Cannot start: %s\n' "$1" >&2; exit 1; }

[ -x "$PY" ] || fail ".venv-ingest is missing. See docs/QUICKSTART_LOCAL.md."
[ -f .env ] || fail ".env is missing. Run ./scripts/init_local_env.sh."
docker info >/dev/null 2>&1 || fail "Docker Desktop is not running."
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  docker compose --env-file .env -f docker/docker-compose.yml stop backend >/dev/null 2>&1
  lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1 && fail "something else holds port 8000."
fi
lsof -nP -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN >/dev/null 2>&1 && fail "port $FRONTEND_PORT is in use."

echo "Starting the stores"
docker compose --env-file .env -f docker/docker-compose.yml up -d --wait postgres qdrant minio >/dev/null 2>&1 \
  || fail "the database, vector store or file store did not start."

if ! curl -fsS --max-time 3 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  echo "Starting Ollama"
  (open -a Ollama 2>/dev/null || nohup ollama serve >"$LOGS/ollama.log" 2>&1 &)
  for _ in $(seq 1 30); do
    curl -fsS --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1 && break
    sleep 2
  done
fi
curl -fsS --max-time 3 http://127.0.0.1:11434/api/version >/dev/null 2>&1 || fail "Ollama did not start."

set -a
# shellcheck disable=SC1091
. ./.env
set +a
export QDRANT_URL=http://localhost:6333 S3_ENDPOINT_URL="http://localhost:${MINIO_PORT:-9000}"
export LEGAL_KB_ROOT="$ROOT/data/legal_kb" HF_HUB_OFFLINE=1 HF_HOME="$ROOT/data/legal_kb/cache/models"
export JOB_WORKER_ENABLED=true WARM_QUERY_MODELS_ON_STARTUP=true
# One presenter, asking quickly, must not meet the per-user limits meant for a public host.
export SYNC_DEEP_REQUESTS_PER_MINUTE=30 FAST_REQUESTS_PER_MINUTE=120 JOB_ENQUEUES_PER_MINUTE=60 LLM_SYNC_REQUESTS_PER_MINUTE=30
export CORS_ORIGINS="http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT"

echo "Bringing the database up to date"
(cd backend && "$PY" -m alembic upgrade head >"$LOGS/migrate.log" 2>&1) || fail "migration failed: see $LOGS/migrate.log"

echo "Building the frontend"
if [ ! -d frontend/node_modules ]; then npm --prefix frontend ci >"$LOGS/npm.log" 2>&1 || fail "npm ci failed: see $LOGS/npm.log"; fi
(cd frontend && NEXT_PUBLIC_API_URL="http://localhost:8000" npm run build >"$LOGS/build.log" 2>&1) \
  || fail "the frontend build failed: see $LOGS/build.log"

pids=()
stop() { for pid in "${pids[@]:-}"; do [ -n "$pid" ] && kill "$pid" 2>/dev/null; done; }
trap stop EXIT INT TERM

echo "Starting the API and loading the models (about a minute)"
(cd backend && exec caffeinate -i "$PY" -m uvicorn main:app --host 127.0.0.1 --port 8000 >"$LOGS/backend.log" 2>&1) &
pids+=("$!")
ready=false
for _ in $(seq 1 150); do
  if curl -fsS --max-time 3 http://127.0.0.1:8000/health/ready >/dev/null 2>&1; then ready=true; break; fi
  sleep 2
done
[ "$ready" = true ] || fail "the API did not become ready: see $LOGS/backend.log"

(cd frontend && exec npx --yes serve@14.2.4 out -l "$FRONTEND_PORT" >"$LOGS/frontend.log" 2>&1) &
pids+=("$!")

if [ "${1:-}" = "--seed" ]; then
  echo "Loading demo cases and warming the demo questions (several minutes)"
  "$PY" scripts/seed_demo.py || echo "Seeding had a problem: read the lines above."
fi

printf '\nCorpusil is ready: http://localhost:%s\nCollection: %s\nLogs: %s\nStop with Ctrl+C.\n\n' \
  "$FRONTEND_PORT" "$QDRANT_GLOBAL_COLLECTION" "$LOGS"
wait
