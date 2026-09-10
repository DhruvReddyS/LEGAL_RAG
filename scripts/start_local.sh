#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/.env"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
PORT="${1:-5176}"

fail() {
  printf 'Local startup: %s\n' "$1" >&2
  exit 1
}

case "$PORT" in
  ''|*[!0-9]*) fail "Port must be a number, for example 5176." ;;
esac

command -v docker >/dev/null 2>&1 || fail "Install and open Docker Desktop first."
command -v npm >/dev/null 2>&1 || fail "Install Node.js and npm first."
command -v curl >/dev/null 2>&1 || fail "curl is required."
test -f "$ENV_FILE" || fail "Run: cp .env.example .env, then replace every CHANGE_ME value."
docker info >/dev/null 2>&1 || fail "Docker Desktop is installed but not running."

if ! curl --fail --silent --max-time 3 http://127.0.0.1:11434/api/version >/dev/null; then
  command -v ollama >/dev/null 2>&1 || fail "Install Ollama and run: ollama serve"
  printf 'Starting Ollama...\n'
  ollama serve >"${TMPDIR:-/tmp}/legal-rag-ollama.log" 2>&1 &
  for _ in $(seq 1 30); do
    curl --fail --silent --max-time 3 http://127.0.0.1:11434/api/version >/dev/null && break
    sleep 1
  done
fi
curl --fail --silent --max-time 3 http://127.0.0.1:11434/api/version >/dev/null \
  || fail "Ollama did not become ready. Check ${TMPDIR:-/tmp}/legal-rag-ollama.log."

configured_origins="$(sed -n 's/^CORS_ORIGINS=//p' "$ENV_FILE" | tail -n 1)"
configured_origins="${configured_origins:-http://localhost:3000,http://127.0.0.1:3000}"
local_origins="$configured_origins,http://localhost:$PORT,http://127.0.0.1:$PORT"

printf 'Starting the API and data services...\n'
CORS_ORIGINS="$local_origins" docker compose --env-file "$ENV_FILE" \
  -f "$COMPOSE_FILE" up -d --build

printf 'Waiting for model warm-up and API readiness...\n'
ready=false
for _ in $(seq 1 90); do
  if curl --fail --silent --max-time 3 http://127.0.0.1:8000/health/ready >/dev/null; then
    ready=true
    break
  fi
  sleep 2
done
test "$ready" = true || fail "Backend readiness failed. Run: docker compose --env-file .env -f docker/docker-compose.yml logs backend"

if test ! -d "$FRONTEND_DIR/node_modules"; then
  printf 'Installing frontend packages...\n'
  npm --prefix "$FRONTEND_DIR" ci
fi

printf '\nCorpusil is ready.\n'
printf 'Frontend: http://localhost:%s\n' "$PORT"
printf 'API:      http://localhost:8000\n'
printf 'Stop the frontend with Ctrl+C. Docker services remain available for the next run.\n\n'

cd "$FRONTEND_DIR"
exec npm run dev -- --port "$PORT"
