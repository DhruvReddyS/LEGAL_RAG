#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${PROJECT_DIR}/docker/docker-compose.yml"
ENV_FILE="${PROJECT_DIR}/.env"
APP_PATH="${PROJECT_DIR}/frontend/src-tauri/target/release/bundle/macos/Aegis Legal Intelligence.app"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy .env.example to .env and add the required secrets first." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop is not running. Start it, then run this command again." >&2
  exit 1
fi

echo "Starting PostgreSQL, Qdrant, MinIO and the API..."
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d

echo "Waiting for the API and warmed retrieval models..."
api_ready=false
for _attempt in $(seq 1 90); do
  if curl --silent --fail --max-time 2 http://localhost:8000/health >/dev/null; then
    api_ready=true
    break
  fi
  sleep 2
done

if [[ "${api_ready}" != "true" ]]; then
  echo "The API did not become healthy within 180 seconds." >&2
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps >&2
  exit 1
fi

if ! curl --silent --fail --max-time 2 http://localhost:11434/api/tags >/dev/null; then
  echo "Warning: Ollama is not reachable on port 11434. Fast Research works, but Deep Review needs Ollama." >&2
fi

if [[ ! -d "${APP_PATH}" ]]; then
  echo "The desktop package is missing; building it now..."
  if [[ -f "${HOME}/.cargo/env" ]]; then
    # shellcheck disable=SC1091
    source "${HOME}/.cargo/env"
  fi
  (cd "${PROJECT_DIR}/frontend" && npm run desktop:build)
fi

echo "Opening Aegis Legal Intelligence..."
open -n "${APP_PATH}"
