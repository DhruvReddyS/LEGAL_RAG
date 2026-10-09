# Starting Corpusil locally

Every command runs from the repository root.

## Prerequisites

- **Docker Desktop**, installed *and running*. It hosts PostgreSQL, Qdrant,
  MinIO and the backend API.
- **Ollama**, running natively — not in a container. A containerised Ollama has
  no GPU access and silently falls back to CPU.
- **Node.js and npm**, for the frontend.

## 1. Configuration

```bash
./scripts/init_local_env.sh
```

Creates `.env` from `.env.example` and generates the four local secrets
(two JWT signing keys, the MinIO root user and password). It keeps an existing
`.env` untouched, so it is safe to re-run.

## 2. Reasoning model

```bash
ollama serve &
ollama pull qwen3:14b
```

Roughly 9 GB, so this is the slow step on a first run. Let it finish before
step 3: the backend's readiness check depends on the model being present.

## 3. Start

```bash
./scripts/start_local.sh 3000
```

The script brings up the Docker services, waits for
`http://127.0.0.1:8000/health/ready`, installs frontend packages if
`frontend/node_modules` is missing, then runs the Next dev server in the
foreground. It prints `Corpusil is ready.` with both URLs.

- Interface: <http://localhost:3000>
- Ingestion status: <http://localhost:3000/ingestion>
- API: <http://localhost:8000>

The port argument is optional and defaults to 5176.

`Ctrl+C` stops the frontend only. The Docker services stay up for the next run;
stop them with `docker compose --env-file .env -f docker/docker-compose.yml stop`.
Do not use `down -v` unless the database, vector and object data are
intentionally being deleted.

## When startup fails

The script names the failed check. For a readiness failure the cause is in the
backend container:

```bash
docker compose --env-file .env -f docker/docker-compose.yml logs backend | tail -40
```

## A note on the ingestion page

`/ingestion` reports corpus build progress from the ingestion checkpoint. A
fresh clone has no checkpoint, so the page correctly reads **Not started** at
0% until an ingestion run has been started. Running one is a separate
operation, covered in [`OPERATIONS.md`](OPERATIONS.md).
