#!/bin/sh
set -eu

alembic upgrade head
python -m app.ingestion.init_qdrant
python -m app.ingestion.init_storage
exec "$@"
