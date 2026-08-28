# Multi-device deployment and scaling architecture

Updated: **2026-08-27 IST**

## Decision

Other devices must not attempt to use `localhost` for shared data or inference.
For a lab, college network or production deployment, run one central service
plane and let every browser/Tauri client connect to it over HTTPS:

```text
Mac / Windows / browser clients
              │
              ▼
      HTTPS reverse proxy / API gateway
              │
       ┌──────┴─────────┐
       ▼                ▼
 stateless FastAPI   background jobs
       │                │
       ├──── PostgreSQL / PgBouncer
       ├──── Qdrant cluster
       ├──── S3-compatible object storage
       └──── private inference gateway ─── Ollama now; vLLM/SGLang at scale
```

Only ports 443 (and optionally 80 for redirect) should be reachable by client
devices. Ollama `11434`, PostgreSQL `5432`, Qdrant `6333/6334`, MinIO admin/API,
Redis and worker ports remain on a private network. Ollama has no application
RBAC boundary and must never be exposed directly to users.

## What is implemented now

- The Tauri/web API endpoint is build-configurable with `NEXT_PUBLIC_API_URL`.
- The packaged desktop CSP accepts local development endpoints and TLS API
  endpoints while continuing to block arbitrary non-TLS remote connections.
- FastAPI CORS origins are explicit and deployment-configurable through
  `CORS_ORIGINS`; wildcard credentialed CORS is rejected at startup.
- Cookie security is configurable through `COOKIE_SECURE` and
  `COOKIE_SAMESITE`; production can use secure cross-origin cookies.
- The local Docker-to-host model path remains
  `OLLAMA_BASE_URL=http://host.docker.internal:11434`.
- Deployment configuration has automated tests.

## Central server configuration

Set these on the server without committing real secrets:

```dotenv
APP_ENV=production
CORS_ORIGINS=https://app.aegis.example,http://tauri.localhost,tauri://localhost
COOKIE_SECURE=true
COOKIE_SAMESITE=none
OLLAMA_BASE_URL=http://inference.internal:11434
OLLAMA_MODEL=qwen3-14b-16k:latest
```

Use strong independent JWT, database and object-storage secrets. Terminate TLS
at a reverse proxy or managed gateway and proxy `https://api.aegis.example` to
FastAPI. Add rate limits, request-size limits, access logs and a strict HSTS
policy at that boundary.

Build a device package for that environment:

```bash
cd frontend
NEXT_PUBLIC_API_URL=https://api.aegis.example npm run desktop:build
```

The server hostname is compiled into the static bundle. This is appropriate for
a fixed college/on-prem deployment. Runtime server profiles plus refresh-token
storage in the operating-system keychain/Stronghold are a remaining hardening
item before distributing one desktop binary across unrelated deployments.

## Three rollout profiles

### Profile A — single-machine capstone demo (current)

All services and Tauri run on one Apple Silicon Mac. Use
`./scripts/start_desktop.sh`. This is fully accepted for local demonstration.

### Profile B — LAN/college pilot

Use one server with a stable private DNS name and a locally trusted TLS
certificate. Client devices receive only the web URL or environment-specific
Tauri package. Do not expose infrastructure ports on the LAN. Back up PostgreSQL,
MinIO and Qdrant snapshots and test restoration before adding real users.

### Profile C — production/large corpus

Run multiple stateless API replicas behind a gateway. Separate query serving
from OCR/ingestion/document-analysis workers. Add Redis for scope-aware cache,
rate limits, distributed locks and job state; PgBouncer for connection pooling;
Qdrant replicas/snapshots; versioned S3 storage; and a dedicated batched GPU
inference service. Autoscale API and workers independently. Never create one
copy of BGE and the LLM inside every web worker.

## Scale gates

1. **Security:** TLS, explicit origins, secure cookies/keychain tokens, rate
   limits, secret manager, audit retention and penetration testing.
2. **Isolation:** repeat cross-owner/cross-role tests at concurrency 1, 10 and
   25; zero private result may be cached without role, owner and case IDs in the
   key.
3. **Latency:** Fast p95 under five seconds; Deep returns a job/stream quickly
   and completes separately without blocking Fast traffic.
4. **Reliability:** durable queues, idempotent jobs, retry/dead-letter policy,
   circuit breakers, backups, Qdrant snapshots and restore drills.
5. **Corpus quality:** Bronze/Silver/Gold governance, shadow collections,
   retrieval evaluation and atomic alias promotion for every release.
6. **Observability:** p50/p95/p99 by stage, queue depth, tokens/sec, cache hits,
   errors, retry rate, memory, GPU utilization and per-role usage quotas.

## Capacity direction

The current 381-document corpus contains 25,517 searchable passages. The
measured planning ratio is about 67 passages per comparable document. A pilot
addition of 1,000 comparable sources therefore implies roughly 67,000 more
passages and 1.6 GiB of original PDFs, before replicas/backups. Judgment sets
vary widely; run a 10,000-point pilot and measure compacted Qdrant snapshots
before purchasing production storage.

## Remaining implementation order

1. Finish Document Analyzer and Source Provenance/Evidence Inspector acceptance.
2. Add durable Redis/PostgreSQL jobs for Deep Review, OCR, indexing and exports.
3. Add SSE progress/agent-trace streaming and cancellation.
4. Split embedding/reranking/inference from stateless API replicas.
5. Add Legal Document Studio, immutable versions and PDF/DOCX export.
6. Add judgment summarizer/similarity and the amendment/current-law graph.
7. Add feedback, evaluation and administrator quality dashboards.
8. Add P3 timeline, evidence mapping, missing-information and contradiction
   intelligence.
9. Add P4 police investigation and advocate argument–precedent intelligence.
10. Add the bounded P5 Virtual Courtroom, P6 academic ablation suite and only
    then P7 multilingual/voice/offline stretch features.

Each phase must pass functional, grounding, RBAC, latency and UI acceptance
before it is marked complete. The platform must never imply that unfinished
features are production-ready.
