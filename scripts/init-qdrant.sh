#!/bin/sh
set -eu

docker compose --env-file .env -f docker/docker-compose.yml exec -T \
    backend python -m app.ingestion.init_qdrant
