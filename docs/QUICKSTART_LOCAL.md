# Starting Corpusil locally

Every command runs from the repository root.

## What a fresh clone can and cannot do

The law is not in this repository. The 419 source PDFs and the vector index are too
large and are deliberately not committed, so a fresh clone starts with an **empty
legal corpus**: the collection exists and holds nothing.

| Works on a fresh clone | Does not work until a corpus is loaded |
| --- | --- |
| Accounts, roles, the admin console | Answers grounded in the law, with citations (Ask and Research) |
| Cases, notes, witnesses, exhibits, custody, remand, diary | Law lookup text and the Act browser (`/law/acts` reports not ready) |
| Time limits, compliance, offence elements, search check | Precedents, treatment check and other tools that read the judgments held |
| Uploading evidence and searching it inside its own case | Authorities inserted into drafts |
| Case file and draft exports to Word | Citation checks against the corpus |
| The citizen rights pages, which ship with the frontend | |

Three ways to get a corpus. None of them is a single command:

- **A corpus pack from whoever runs this project.** Restores the public index without
  rebuilding it: `python3 scripts/build_offline_corpus_pack.py restore <pack.tar>
  --qdrant-url http://localhost:6333 --legal-kb-root data/legal_kb`. No pack is
  published with this repository, so ask for one.
- **The PDFs, then a build.** Put them under `data/legal_kb/raw/` where
  `data/legal_kb/metadata/canonical_documents.jsonl` expects them, then follow
  "Corpus ingestion" in [`04-OPERATIONS.md`](04-OPERATIONS.md). It takes hours.
- **Fetching from the sources.** `scripts/fetch_sources.py` downloads a source list
  from `data/source_materials/` into `candidate_imports`. Those are candidates, not the
  corpus: government hosts refuse some requests, and each file still has to be
  reviewed and staged before it is indexed.

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

Creates `.env` from `.env.example` and generates the local secrets: two JWT signing
keys, the MinIO root user and password, and the database password, with a
`DATABASE_URL` that matches it. It warns if the database port is already in use. It
keeps an existing `.env` untouched, so it is safe to re-run.

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

The script builds and brings up the Docker services, waits for
`http://127.0.0.1:8000/health/ready`, installs frontend packages if
`frontend/node_modules` is missing, then runs the Next dev server in the
foreground. It prints `Corpusil is ready.` with both URLs.

The first run is slow: the image builds, and the API downloads the embedding and
reranking models (several GB) before it answers. The script waits up to 30 minutes;
set `STARTUP_WAIT_SECONDS` to change that. Follow the download with
`docker compose --env-file .env -f docker/docker-compose.yml logs -f backend`.

- Interface: <http://localhost:3000>
- Ingestion status: <http://localhost:3000/ingestion>
- API: <http://localhost:8000>

The port argument is optional and defaults to 5176.

`Ctrl+C` stops the frontend only. The Docker services stay up for the next run;
stop them with `docker compose --env-file .env -f docker/docker-compose.yml stop`.
Do not use `down -v` unless the database, vector and object data are
intentionally being deleted.

## 4. Accounts

Anyone can register a citizen account from the sign-in screen. Police and advocate
accounts are created by an administrator, so create the administrator first:

```bash
docker compose --env-file .env -f docker/docker-compose.yml exec backend \
  python create_admin_account.py --name "Your Name" --email you@example.com
```

It runs in the backend container, so it needs no Python setup on this machine. It asks
for a password and refuses to create a second administrator. Sign in, open the admin
console and add the other accounts under Users. An account made there has to change
its password at first sign-in. Clearing a forced reset in the console does not lift
that first change, and the row says so.

## When startup fails

The script names the failed check. For a readiness failure the cause is in the
backend container:

```bash
docker compose --env-file .env -f docker/docker-compose.yml logs backend | tail -40
```

## A note on the ingestion page

`/ingestion` reports corpus build progress from the ingestion checkpoint. A
fresh clone has no checkpoint, so the page correctly reads **Not started** at
0% until an ingestion run has been started. Running one needs the PDFs, as above, and
is covered in [`04-OPERATIONS.md`](04-OPERATIONS.md).

## Running the tests

```bash
python3 -m venv .venv-ingest && .venv-ingest/bin/pip install -r backend/requirements-dev.txt
scripts/run_backend_tests.sh
```

This starts a throwaway stack with its own volumes and ports, so it cannot reach
your live database, corpus or object store. Remove it afterwards with
`scripts/run_backend_tests.sh --down`.

Frontend tests need no services:

```bash
cd frontend && npm test && npx playwright install chromium && npm run test:e2e
```

Plain `pytest` from `backend/` needs nothing running: tests that need services
skip. The suite refuses any database whose name does not end in `_test`.

## If port 5432 is already taken

If another Postgres runs on this machine, `init_local_env.sh` says so. Change the port
in both `POSTGRES_PORT` and `DATABASE_URL` in `.env` to a free one, so compose can start
and native backend runs and scripts do not connect to the other server.
