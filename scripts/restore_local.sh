#!/usr/bin/env bash
# Replace the local stack's state with a backup from backup_local.sh.
#
#   scripts/restore_local.sh --yes backups/2026-11-05_143000
#
# This overwrites the database, the Qdrant collections in the backup and all MinIO
# data. It refuses without both --yes and a named folder, and it checks the whole
# backup against its MANIFEST before changing anything. Stop the backend first.
#
# Everything goes through this project's own compose containers, and no secret is
# read from .env or printed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
COMPOSE_FILE="$ROOT/docker/docker-compose.yml"
MINIO_VOLUME="multi-agent-legal-rag_minio_data"

usage() {
  sed -n '2,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

fail() {
  printf 'Restore: %s\n' "$1" >&2
  exit "${2:-1}"
}

CONFIRMED=false
FOLDER=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes)
      CONFIRMED=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      fail "Unknown argument: $1" 2
      ;;
    *)
      [ -z "$FOLDER" ] || fail "Name one backup folder only." 2
      FOLDER="$1"
      shift
      ;;
  esac
done

[ "$CONFIRMED" = true ] || fail "This overwrites all local data. Refusing without --yes." 2
[ -n "$FOLDER" ] || fail "Name the backup folder to restore. Refusing without one." 2
[ -d "$FOLDER" ] || fail "No such folder: $FOLDER" 2
FOLDER="$(cd "$FOLDER" && pwd)"
case "$FOLDER" in
  *.partial) fail "$FOLDER is an incomplete backup." 2 ;;
esac
[ -f "$FOLDER/MANIFEST" ] || fail "$FOLDER has no MANIFEST, so it is not a complete backup." 2
[ -f "$FOLDER/postgres/database.dump" ] || fail "$FOLDER has no database dump." 2
[ -f "$FOLDER/minio/data.tar" ] || fail "$FOLDER has no MinIO archive." 2

command -v shasum >/dev/null 2>&1 || fail "shasum is required."
printf 'Checking the backup against its MANIFEST...\n'
(cd "$FOLDER" && grep -v '^#' MANIFEST | shasum -a 256 --check --quiet) \
  || fail "The backup does not match its MANIFEST. Nothing has been changed."

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

[ -f "$ENV_FILE" ] || fail "No .env at the project root."
command -v docker >/dev/null 2>&1 || fail "Docker is required."
command -v curl >/dev/null 2>&1 || fail "curl is required."
docker info >/dev/null 2>&1 || fail "Docker is not running."
for service in postgres qdrant minio; do
  [ -n "$(compose ps --status running -q "$service")" ] || fail "The $service container is not running."
done
docker volume inspect "$MINIO_VOLUME" >/dev/null 2>&1 || fail "The MinIO volume was not found."

# A running backend would write into a database that is being replaced.
[ -z "$(compose ps --status running -q backend)" ] || fail "The backend container is running. Stop it first."
if (exec 3<>/dev/tcp/127.0.0.1/8000) 2>/dev/null; then
  fail "Something is listening on port 8000. Stop the backend first."
fi

QDRANT_URL="http://$(compose port qdrant 6333)"
trap 'printf "Restore: stopped part way. The stack may hold a mix of old and new data. Run it again before using it.\n" >&2' ERR

printf 'Postgres...\n'
# The variables expand inside the container, from the container's own environment.
# shellcheck disable=SC2016
compose exec -T postgres sh -c 'exec pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error' \
  < "$FOLDER/postgres/database.dump"

printf 'Qdrant...\n'
for snapshot in "$FOLDER"/qdrant/*.snapshot; do
  [ -f "$snapshot" ] || continue
  collection="$(basename "$snapshot" .snapshot)"
  printf '  %s\n' "$collection"
  curl --fail --silent --show-error -X POST \
    "$QDRANT_URL/collections/$collection/snapshots/upload?wait=true&priority=snapshot" \
    -F "snapshot=@$snapshot" >/dev/null
done

printf 'MinIO...\n'
compose stop minio
# shellcheck disable=SC2016
compose run --rm --no-deps -T -v "$MINIO_VOLUME:/minio_data" --entrypoint sh postgres -c \
  'find /minio_data -mindepth 1 -delete && exec tar -C /minio_data -xf -' \
  < "$FOLDER/minio/data.tar"
compose up -d --wait minio

trap - ERR
printf 'Restore finished from %s\n' "$FOLDER"
printf 'Run the migrations before starting the backend, in case this backup is older than the code.\n'
