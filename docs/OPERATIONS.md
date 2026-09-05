# Corpusil — Operations

Running it, releasing it, and sharing one instance with a small group. The
architecture behind these procedures is in [PRD.md](PRD.md); current pending
work is in [NEXT_STEPS.md](NEXT_STEPS.md).

---

## 1. Local development

Every service is loopback-only. Nothing but Tailscale (§4) ever exposes a port.

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

Ollama runs **natively**, not in a container — it needs direct GPU access, and a
containerised Ollama silently falls back to CPU:

```bash
ollama serve
ollama pull qwen3-14b-16k
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
curl localhost:8000/health/ready    # dependencies are reachable
python scripts/verify_retrieval_health.py
```

`/health/ready` reports each dependency separately and never raises — a degraded
dependency must be reportable, not fatal to the report.

---

## 2. Corpus ingestion

```bash
# Full build
cd backend && python -m app.ingestion.pipeline --resume

# Re-chunk only: re-runs parsing, chunking and embedding from cached
# extracted text, without re-OCRing 381 documents
python -m app.ingestion.pipeline --rechunk --resume

# Supervised: brings the stack up, resumes, repeats until complete
./scripts/run_rebuild.sh global_legal_corpus_v2
```

A build takes hours and will be interrupted. It checkpoints per document, so a
resume costs one document rather than the run.

**Never run ingestion and serving at the same time on a 24 GB machine.** The 14B
model, both encoders and a second copy of BGE-M3 in the ingestion process do not
fit together; the result is tens of gigabytes of swap and a rebuild that crawls.
See PRD §14.5.

### Building a new index in parallel

```bash
QDRANT_GLOBAL_COLLECTION=global_legal_corpus_v2 python -m app.ingestion.pipeline --rechunk --resume
```

Each collection keeps its own checkpoint ledger, so two builds never skip each
other's documents. Cutover is a single environment variable, which makes
rollback a restart rather than another re-index.

---

## 3. Desktop release

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

## 4. Sharing one instance with a small group

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
because the API is a bottleneck. Retrieval answers in ~90 ms; a Deep request
takes 78–85 s and holds the model for its duration. Growth means more generation
capacity — a second Ollama host, or a smaller model for non-adjudicating roles —
not more API workers.

---

## 5. Demo walkthrough

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

## 6. Backups

State lives in three Docker volumes — PostgreSQL, Qdrant and MinIO — plus
`data/legal_kb/` on disk. `docker compose down -v` **deletes all three volumes**.
Do not run it unless you intend to lose the database, the index and every
uploaded document.

The corpus can be rebuilt from `data/legal_kb/` and the manifest. Case documents
and user accounts cannot.
