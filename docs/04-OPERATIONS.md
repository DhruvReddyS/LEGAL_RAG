# 04 — Operations

*How to run it, build the corpus, and cut a release. Commands are meant to be
copied.*

---

## 1. The system in operation

### 1.1 Running it

```bash
docker compose --env-file .env -f docker/docker-compose.yml up -d --wait postgres qdrant minio
cd backend && python -m alembic upgrade head
python -m app.ingestion.init_qdrant && python -m app.ingestion.init_storage
python -m uvicorn main:app --host 127.0.0.1 --port 8000
cd ../frontend && npm run dev
```

### 1.2 Configuration that matters

| Setting | Default | Note |
|---|---|---|
| `QDRANT_GLOBAL_COLLECTION` | `global_legal_corpus` | **The cutover switch.** Building a new index in parallel and switching is one env var, so rollback is a restart |
| `CROSS_ENCODER_RERANKING_ENABLED` | `false` | §5.6 |
| `REPEALED_RANK_PENALTY` | `3` | Rank places, not score |
| `OLLAMA_MODEL` | `qwen3-14b-16k` | A model advertising fewer than 8B parameters **refuses to boot** (§14.3) |
| `EXPECT_ACCELERATED_INFERENCE` | `false` | Set true to fail startup on CPU inference |

`.env` describes the **host's** view so a natively-run backend works; the compose
file pins the container-internal addresses itself. Configuration is anchored to
the repository, not the working directory — a relative `.env` meant the same
command loaded different config from different folders, and fell back to
development credentials without saying so.

### 1.3 The model-tier boot assertion

One model performs reasoning, verification and response generation. A weaker
model there does not fail visibly — it **approves claims it should refuse**,
which raises the verification score while making answers less trustworthy. The
application refuses to start if `OLLAMA_MODEL` advertises fewer than 8B
parameters, unless `ALLOW_SMALL_REASONING_MODEL=1` is set deliberately.

### 1.4 Durable jobs

Deep requests exceeding the sync budget become jobs in PostgreSQL. A worker
claims them with `FOR UPDATE SKIP LOCKED`, so several workers are safe. Progress
is polled; an SSE stream exists and is tested but unused by the client.

### 1.5 Hardware

Measured on Apple M5 Pro, 24 GB unified memory:

| Component | Resident |
|---|---:|
| `qwen3-14b-16k` (100% GPU, 16,384 ctx) | 11.66 GB |
| BGE-M3 (MPS, fp16) | 1.14 GB |
| Cross-encoder (MPS, fp16) | 1.13 GB |
| Containers + Docker VM | ~2.13 GB |

**Serving alone fits at ~20–21 GB. Serving plus ingestion does not** — that
combination produced 30.6 GB of swap and 0.16 GB free. Model weights are *wired*
and cannot page out.

A two-tier model strategy does not resolve this: 11.66 + 2.50 GB means both
tiers cannot be resident, so "two-tier" here means swapping models with a reload
each time.

---

---

Running it, releasing it, and sharing one instance with a small group. The
architecture behind these procedures is in [02-ARCHITECTURE](02-ARCHITECTURE.md); current pending
work is in [06-PLAN](06-PLAN.md).

---

## 2. Local development

Every service is loopback-only. Nothing but Tailscale (§4) ever exposes a port.

For the normal full-stack development setup, one command starts the data
services, API and frontend. It uses port 5176 so port 3000 can remain assigned
to another project:

```bash
./scripts/start_local.sh
```

Pass a different frontend port only when needed, for example
`./scripts/start_local.sh 5180`.

```bash
# 1. Infrastructure
docker compose --env-file .env -f docker/docker-compose.yml up -d --wait postgres qdrant minio

# 2. Schema, collections, buckets
cd backend
python -m alembic upgrade head
python -m app.ingestion.init_qdrant
python -m app.ingestion.init_storage

# 3. Backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 4. Interface
cd ../frontend && npm run dev
```

### Unload the reasoning model before a corpus rebuild

This host has 24 GB of unified memory and `qwen3-14b-16k` holds 11.7 GB of it,
resident for 30 minutes after the last query. Start a rebuild while it is
loaded and the embedder competes with it: measured 34.2 GB of swap in use and
BGE-M3 taking **4.75 seconds** for a single-item batch, which is a rebuild
measured in days rather than hours.

Unloading it took swap to 18.1 GB and the encoder to **1.4-4.2 items a
second** -- the same work, an order of magnitude faster, from one API call:

```bash
curl -s http://localhost:11434/api/generate \
  -d '{"model":"qwen3-14b-16k:latest","keep_alive":0,"prompt":"","stream":false}'
```

`scripts/run_rebuild.sh` now does this itself before ensuring the collection
exists, so it is not something anyone has to remember. The model reloads on
the next query in about ten seconds, and nothing should be querying during a
rebuild.

This note corrects a standing assumption. "Ingestion makes this machine swap
heavily, around 20 GB" has been recorded as a property of ingestion and worked
around for weeks, including by scheduling measurement windows around it. It is
a property of running both models at once.

### The containerised backend will steal port 8000 from a native one

`docker/docker-compose.yml` gives the `backend` service
`restart: unless-stopped`. Once it has run, Docker brings it back on the next
engine start, it binds `127.0.0.1:8000`, and a natively-run backend started
afterwards fails with `address already in use` and exits.

The failure is quiet and expensive. The container is built from the CPU torch
wheel, so it resolves `EMBEDDING_DEVICE=auto` to `cpu` while the host resolves
it to `mps`. Everything answers, `/health/ready` reports ready, and retrieval
is several times slower. On 8 October this consumed a full latency measurement
window before `/health/ready`'s `inference` block showed `"embedding": "cpu"`
and gave it away.

So when running the backend natively, stop the container first and check what
is actually listening:

```bash
docker compose --env-file .env -f docker/docker-compose.yml stop backend
lsof -nP -iTCP:8000 -sTCP:LISTEN
curl -s localhost:8000/health/ready | python3 -m json.tool   # inference must say mps
```

`/health/ready` reports the resolved device for exactly this reason. Read it
rather than assuming which process answered.

Ollama runs **natively**, not in a container — it needs direct GPU access, and a
containerised Ollama silently falls back to CPU:

```bash
ollama serve
ollama pull qwen3:14b
```

### Configuration

`.env` describes the **host's** view of the world, so a natively-run backend
works. The compose file pins the container-internal addresses (`qdrant:6333`,
`minio:9000`, `host.docker.internal:11434`) itself, so those two never fight.

Configuration is anchored to the repository rather than the working directory.
A relative `.env` meant the same command loaded different configuration
depending on which folder it ran from, and fell back to development credentials
without saying so.

Never commit `.env`, signing keys, real case data or passwords.

### Health

```bash
curl localhost:8000/health/live     # process is up
curl localhost:8000/health/ready    # dependencies and model are reachable
python scripts/verify_retrieval_health.py
```

`/health/ready` reports each dependency separately and never raises — a degraded
dependency must be reportable, not fatal to the report.

---

## 3. Corpus ingestion

```bash
# Full build
cd backend && python -m app.ingestion.pipeline --resume

# Re-chunk only: re-runs parsing, chunking and embedding from cached
# extracted text, without re-OCRing every document
python -m app.ingestion.pipeline --rechunk --resume

# Supervised: brings the stack up, resumes, repeats until complete
./scripts/run_rebuild.sh global_legal_corpus_v3
```

A build takes hours and will be interrupted. It checkpoints per document, so a
resume costs one document rather than the run.

**Never run ingestion and serving at the same time on a 24 GB machine.** The 14B
model, both encoders and a second copy of BGE-M3 in the ingestion process do not
fit together; the result is tens of gigabytes of swap and a rebuild that crawls.
See PRD §14.5.

### Building a new index in parallel

```bash
QDRANT_GLOBAL_COLLECTION=global_legal_corpus_v3 python -m app.ingestion.pipeline --rechunk --resume
```

Each collection keeps its own checkpoint ledger, so two builds never skip each
other's documents. Cutover is a single environment variable, which makes
rollback a restart rather than another re-index.

---

## 4. Desktop release

Distributed as a signed Tauri client for macOS and Windows, published through
GitHub Releases with the built-in updater.

- Version is set in `frontend/src-tauri/Cargo.toml` and its Tauri config;
  `scripts/check_release_version.py` fails the build if they disagree.
- Installers and the update manifest are produced by the release workflow.
- Signing keys live in CI secrets, never in the repository.
- **Do not publish corpus material in a public release.** Much of it is
  redistributable only from its official source.

The client is a shell. It does not embed credentials, and it reaches Ollama on
the host rather than bundling a model.

---

## 5. Sharing one instance with a small group

The chosen shape for a pilot: **one backend on the strongest machine, thin
clients over a private Tailscale network.** The alternative — a complete stack
per device — was rejected because it means a full corpus build and a 14B model
on every laptop.

1. On the host: Docker Desktop, Ollama and Tailscale; corpus ingested.
2. Keep FastAPI on `127.0.0.1:8000`. PostgreSQL, Qdrant, MinIO and Ollama stay
   loopback-only.
3. Expose the API to the private network with **Tailscale Serve** over HTTPS.
   **Never Tailscale Funnel, and never a router port forward** — those publish a
   legal corpus and other people's case material to the open internet.
4. Each participant installs Tailscale and accepts the invitation. This is the
   one unavoidable manual step.
5. Create accounts with `scripts/create_admin_account.py` and
   `scripts/create_professional_account.py`. Generate a unique random password
   per person and send each separately.

Run Ollama with a single parallel request on a 24 GB host. Concurrency there
costs memory the machine does not have, and queued requests are better than
swapped ones.

### Capacity

The pilot host serves a handful of users because generation is serialised, not
because the API is a bottleneck. Retrieval answers in ~90 ms; the current
four-question Deep benchmark averages 66.5 s (59.3–85.0 s for the three citizen
questions) and holds the model for its duration. Growth means more generation
capacity — a second Ollama host, or a smaller model for non-adjudicating roles —
not more API workers.

---

## 6. Demo walkthrough

Sign in as each role to show what changes. The corpus is identical; the role
changes the objective, the response contract and the safety boundary.

**Citizen** — ask "What are the rights of a person who has been arrested?" Fast
returns cited passages in well under a second. Open the source inspector to show
the passage, its pages and its currency status. Then ask a corpus gap — "My
landlord will not return my security deposit" — and show that it **declines**
rather than inventing an answer. Then ask something with a repealed source and
show the currency label naming the replacement.

**Police** — create a case, upload a witness statement, and show that the same
question now draws on both public law and that matter's evidence. Signing in as
a different officer and requesting the same case returns **404**, not 403.

**Advocate** — the defence strategy agent produces two-sided analysis including
adverse arguments, refusing to fill a factual gap it was not given.

**Administrator** — user management, corpus statistics and the audit log. A
general search as an administrator reaches **no** private case material; a named
matter does, and is auditable.

> Demo credentials are local capstone accounts only. Do not reuse those
> passwords anywhere, and do not put real case material in a demo instance.

---

## 7. Backups

State lives in three Docker volumes — PostgreSQL, Qdrant and MinIO — plus
`data/legal_kb/` on disk. `docker compose down -v` **deletes all three volumes**.
Do not run it unless you intend to lose the database, the index and every
uploaded document.

The corpus can be rebuilt from `data/legal_kb/` and the manifest. Case documents
and user accounts cannot.

## Rebuilds reuse embeddings

`data/legal_kb/cache/content_embeddings.sqlite` keeps every vector by model and exact
text, so a rebuild only embeds text that changed, and an interrupted run keeps every
finished batch. Deleting the file is safe and costs only time. `--force` ignores it.
A new embedding model starts empty, since the model is part of the key.
