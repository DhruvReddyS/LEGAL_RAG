#!/usr/bin/env bash
# Run on the Mac, from the repository root: ./deploy/oracle/upload_corpus.sh ubuntu@<server-ip>
# Sends a snapshot of the serving collection and the embedding models. Source PDFs stay behind:
# the answers read from the index, and each citation links to its official source.
set -euo pipefail

SERVER="${1:?usage: upload_corpus.sh ubuntu@<server-ip>}"
COLLECTION="${QDRANT_GLOBAL_COLLECTION:-global_legal_corpus_v6}"
QDRANT="${QDRANT_URL:-http://127.0.0.1:6333}"
REMOTE_DIR="${REMOTE_DIR:-LEGAL_RAG}"

echo "Creating a snapshot of ${COLLECTION}"
NAME="$(curl -fsS -X POST "${QDRANT}/collections/${COLLECTION}/snapshots" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["name"])')"
LOCAL="$(mktemp -d)/corpus.snapshot"
curl -fsS "${QDRANT}/collections/${COLLECTION}/snapshots/${NAME}" -o "$LOCAL"
du -h "$LOCAL"

ssh "$SERVER" "mkdir -p ${REMOTE_DIR}/data/legal_kb/cache/models ${REMOTE_DIR}/data/legal_kb/metadata ${REMOTE_DIR}/data/legal_kb/mapping"
rsync -a --partial --info=progress2 "$LOCAL" "${SERVER}:corpus.snapshot"
rsync -a --partial --info=progress2 data/legal_kb/cache/models/ "${SERVER}:${REMOTE_DIR}/data/legal_kb/cache/models/"
rsync -a --partial data/legal_kb/metadata/ "${SERVER}:${REMOTE_DIR}/data/legal_kb/metadata/"
rsync -a --partial data/legal_kb/mapping/ "${SERVER}:${REMOTE_DIR}/data/legal_kb/mapping/"

echo "Restoring on the server"
ssh "$SERVER" "cd ${REMOTE_DIR} && sudo docker compose --env-file .env -f docker/docker-compose.yml -f deploy/oracle/docker-compose.oracle.yml exec -T qdrant true"
ssh "$SERVER" "curl -fsS -X POST 'http://127.0.0.1:6333/collections/${COLLECTION}/snapshots/upload?priority=snapshot' -F 'snapshot=@corpus.snapshot' && rm -f corpus.snapshot"
rm -f "$LOCAL"
echo "Done. Check the point count on the server."
