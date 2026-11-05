#!/usr/bin/env bash
# Back up the local stack's state to one dated folder.
#
#   scripts/backup_local.sh                   into backups/<date>_<time>/
#   scripts/backup_local.sh --dest /some/dir  into /some/dir/<date>_<time>/
#   scripts/backup_local.sh --dry-run         say what would happen, touch nothing
#
# Everything goes through this project's own compose containers. Nothing connects
# to a Postgres on the host, so a different database on localhost:5432 cannot be
# reached by mistake. Credentials stay in the containers' environment: this script
# never reads a secret from .env, and never prints one.
#
# The folder holds private case material and is created readable by you alone.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
COMPOSE_FILE="$ROOT/docker/docker-compose.yml"
# The name: line in the compose file, which fixes the volume's name.
MINIO_VOLUME="multi-agent-legal-rag_minio_data"

usage() {
  sed -n '2,6p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

fail() {
  printf 'Backup: %s\n' "$1" >&2
  exit "${2:-1}"
}

DEST="$ROOT/backups"
DRY_RUN=false
while [ $# -gt 0 ]; do
  case "$1" in
    --dest)
      [ $# -ge 2 ] && [ -n "$2" ] || fail "--dest needs a folder." 2
      DEST="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1" 2
      ;;
  esac
done

STAMP="$(date +%Y-%m-%d_%H%M%S)"
TARGET="$DEST/$STAMP"

if [ "$DRY_RUN" = true ]; then
  printf 'Would write to: %s\n' "$TARGET"
  printf 'Would save: postgres/database.dump, one qdrant/<collection>.snapshot each, minio/data.tar, MANIFEST\n'
  exit 0
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

[ -f "$ENV_FILE" ] || fail "No .env at the project root. Run scripts/init_local_env.sh first."
command -v docker >/dev/null 2>&1 || fail "Docker is required."
command -v curl >/dev/null 2>&1 || fail "curl is required."
command -v python3 >/dev/null 2>&1 || fail "python3 is required."
command -v shasum >/dev/null 2>&1 || fail "shasum is required."
docker info >/dev/null 2>&1 || fail "Docker is not running."
for service in postgres qdrant minio; do
  [ -n "$(compose ps --status running -q "$service")" ] || fail "The $service container is not running."
done
docker volume inspect "$MINIO_VOLUME" >/dev/null 2>&1 || fail "The MinIO volume was not found."

# The container's published address, rather than an assumed port.
QDRANT_URL="http://$(compose port qdrant 6333)"

umask 077
mkdir -p "$DEST"
# Written under a temporary name, so a folder with its final name is a whole backup.
WORK="$TARGET.partial"
[ ! -e "$TARGET" ] && [ ! -e "$WORK" ] || fail "$TARGET already exists."
mkdir -p "$WORK/postgres" "$WORK/qdrant" "$WORK/minio"
trap 'printf "Backup: stopped early. %s is incomplete and can be deleted.\n" "$WORK" >&2' ERR

printf 'Postgres...\n'
# The variables expand inside the container, from the container's own environment.
# shellcheck disable=SC2016
compose exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
  > "$WORK/postgres/database.dump"

printf 'Qdrant...\n'
COLLECTIONS="$(curl --fail --silent --show-error "$QDRANT_URL/collections" \
  | python3 -c 'import json,sys; print("\n".join(c["name"] for c in json.load(sys.stdin)["result"]["collections"]))')"
for collection in $COLLECTIONS; do
  case "$collection" in
    *[!A-Za-z0-9_.-]*) fail "Unexpected collection name: $collection" ;;
  esac
  printf '  %s\n' "$collection"
  SNAPSHOT="$(curl --fail --silent --show-error -X POST "$QDRANT_URL/collections/$collection/snapshots?wait=true" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["name"])')"
  curl --fail --silent --show-error -o "$WORK/qdrant/$collection.snapshot" \
    "$QDRANT_URL/collections/$collection/snapshots/$SNAPSHOT"
  # Left behind, each one would hold a second copy of the collection in the volume.
  curl --fail --silent --show-error -X DELETE "$QDRANT_URL/collections/$collection/snapshots/$SNAPSHOT?wait=true" >/dev/null
done

printf 'MinIO...\n'
# The raw data directory keeps object versions and metadata, which a bucket copy
# would flatten. The Postgres image is used because it is already here and has tar.
compose run --rm --no-deps -T -v "$MINIO_VOLUME:/minio_data:ro" --entrypoint tar postgres -C /minio_data -cf - . \
  > "$WORK/minio/data.tar"

[ -s "$WORK/postgres/database.dump" ] || fail "The database dump is empty."
[ -s "$WORK/minio/data.tar" ] || fail "The MinIO archive is empty."

(
  cd "$WORK"
  {
    printf '# Corpusil backup %s\n' "$STAMP"
    find postgres qdrant minio -type f -print0 | sort -z | xargs -0 shasum -a 256
  } > MANIFEST
)
trap - ERR
mv "$WORK" "$TARGET"
printf 'Backup finished: %s\n' "$TARGET"
printf 'It holds private case material. Keep your .env safe separately: it is not in the backup.\n'
