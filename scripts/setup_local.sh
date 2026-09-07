#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/.env"

fail() {
  printf 'Local setup: %s\n' "$1" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "Install Docker Desktop first."
command -v node >/dev/null 2>&1 || fail "Install Node.js 18+ first."
command -v npm >/dev/null 2>&1 || fail "Install npm first."
command -v curl >/dev/null 2>&1 || fail "curl is required."
docker info >/dev/null 2>&1 || fail "Start Docker Desktop first."

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
  printf 'Created %s from .env.example. Review local secrets before production use.\n' "$ENV_FILE"
fi

if [[ ! -f "$PROJECT_ROOT/frontend/.env.local" ]]; then
  cp "$PROJECT_ROOT/frontend/.env.local.example" "$PROJECT_ROOT/frontend/.env.local"
fi

printf 'Installing frontend dependencies...\n'
(cd "$PROJECT_ROOT/frontend" && npm install)

printf 'Starting PostgreSQL, Qdrant, MinIO, and the backend...\n'
WARM_QUERY_MODELS_ON_STARTUP="${WARM_QUERY_MODELS_ON_STARTUP:-false}" \
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build

printf 'Waiting for the backend health endpoint...\n'
for _ in $(seq 1 90); do
  if curl --fail --silent --max-time 3 http://127.0.0.1:8000/health >/dev/null; then
    printf '\nBackend is ready: http://localhost:8000\n'
    printf 'API docs: http://localhost:8000/docs\n'
    printf '\nStart the frontend in another terminal with:\n'
    printf '  cd "%s/frontend" && npm run dev\n' "$PROJECT_ROOT"
    printf 'Then open http://localhost:3000\n'
    exit 0
  fi
  sleep 2
done

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps >&2
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=80 backend >&2
fail "The backend did not become healthy within three minutes."
