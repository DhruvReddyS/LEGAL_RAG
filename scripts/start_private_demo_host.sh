#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/.env"
MODEL_NAME="${OLLAMA_MODEL:-qwen3-14b-16k:latest}"

fail() {
  printf 'Aegis host setup: %s\n' "$1" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "Install and open Docker Desktop first."
command -v ollama >/dev/null 2>&1 || fail "Install and start Ollama first."
command -v tailscale >/dev/null 2>&1 || fail "Install Tailscale, sign in, and make its CLI available first."
command -v curl >/dev/null 2>&1 || fail "curl is required."
command -v jq >/dev/null 2>&1 || fail "jq is required."
test -f "$ENV_FILE" || fail "Create .env from .env.example and add strong secrets first."

docker info >/dev/null 2>&1 || fail "Docker Desktop is installed but its engine is not running."
curl --fail --silent --max-time 3 http://127.0.0.1:11434/api/version >/dev/null \
  || fail "Ollama is not reachable at http://127.0.0.1:11434."

if ! ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "$MODEL_NAME"; then
  printf 'Installing the shared Ollama model %s...\n' "$MODEL_NAME"
  ollama pull "$MODEL_NAME"
fi

tailscale_state="$(tailscale status --json | jq -r '.BackendState // empty')"
test "$tailscale_state" = "Running" \
  || fail "Tailscale is not connected. Open Tailscale and sign in first."
dns_name="$(tailscale status --json | jq -r '.Self.DNSName // empty' | sed 's/\.$//')"
test -n "$dns_name" || fail "Tailscale did not report a MagicDNS name."

printf 'Starting the private Aegis backend...\n'
APP_ENV=production \
COOKIE_SECURE=true \
COOKIE_SAMESITE=none \
TRUSTED_HOSTS="localhost,127.0.0.1,${dns_name}" \
OLLAMA_MODEL="$MODEL_NAME" \
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build

printf 'Waiting for model warm-up and API readiness...\n'
healthy=false
for _ in $(seq 1 90); do
  if curl --fail --silent --max-time 3 http://127.0.0.1:8000/health >/dev/null; then
    healthy=true
    break
  fi
  sleep 2
done
test "$healthy" = true || fail "The backend did not become healthy within three minutes."

tailscale serve --bg http://127.0.0.1:8000 >/dev/null
private_url="https://${dns_name}"
curl --fail --silent --max-time 10 "${private_url}/health" >/dev/null \
  || fail "Tailscale Serve was configured, but ${private_url}/health is not reachable."

printf '\nAegis private backend is ready.\n'
printf 'Desktop backend URL: %s\n' "$private_url"
printf 'Health check: %s/health\n' "$private_url"
printf 'Model: %s (runs only on this host)\n' "$MODEL_NAME"
printf '\nKeep this computer, Docker Desktop, Ollama, and Tailscale running while friends use Aegis.\n'
