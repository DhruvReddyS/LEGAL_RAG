#!/usr/bin/env bash
# Run the backend suite against its own throwaway stack.
#
#   scripts/run_backend_tests.sh               everything
#   scripts/run_backend_tests.sh -m "not redteam"
#   scripts/run_backend_tests.sh --down        remove the test stack and its data
#
# The stack has its own compose project, volumes and ports, so nothing here can
# reach the live Postgres, the corpus collections or the live object store.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv-ingest/bin/python}"

export POSTGRES_DB=legal_rag_test
export POSTGRES_USER=legal_rag
export POSTGRES_PASSWORD=legal_rag_dev_only
export POSTGRES_PORT=55433
export QDRANT_HTTP_PORT=56333
export QDRANT_GRPC_PORT=56334
export S3_MOCK_PORT=59000

compose() {
  docker compose -p corpusil-test --env-file "$ROOT/.env.example" \
    -f "$ROOT/docker/docker-compose.yml" -f "$ROOT/docker/docker-compose.ci.yml" "$@"
}

if [ "${1:-}" = "--down" ]; then
  compose down -v
  exit 0
fi

export TEST_DATABASE_URL="postgresql+asyncpg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:$POSTGRES_PORT/$POSTGRES_DB"
export DATABASE_URL="$TEST_DATABASE_URL"
export QDRANT_URL="http://127.0.0.1:$QDRANT_HTTP_PORT"
export S3_ENDPOINT_URL="http://127.0.0.1:$S3_MOCK_PORT"
export S3_PUBLIC_ENDPOINT_URL="$S3_ENDPOINT_URL"
export S3_ACCESS_KEY_ID=test-access-key
export S3_SECRET_ACCESS_KEY=test-secret-key
export JOB_WORKER_ENABLED=false
export WARM_QUERY_MODELS_ON_STARTUP=false
export RUN_INTEGRATION=1

compose up -d --wait postgres qdrant s3mock

cd "$ROOT/backend"
"$PY" -m alembic upgrade head
"$PY" -m app.ingestion.init_qdrant
"$PY" -m app.ingestion.init_storage
"$PY" -m pytest -q "$@"
