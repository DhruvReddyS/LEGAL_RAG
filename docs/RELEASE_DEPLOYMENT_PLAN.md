# Release, Deployment, and Data-Flow Plan

## Release model

The GitHub Release is a client distribution channel, not a complete hosted service. The release workflow builds signed Tauri installers and updater metadata for macOS and Windows, creates a draft GitHub Release, verifies its artifacts, and intentionally leaves publication as a manual decision.

The desktop installer contains the statically exported Next.js interface. It does not contain the legal corpus, PostgreSQL, Qdrant, MinIO, Ollama, case files, or server secrets. On first use, the desktop app points to either a local backend or a private HTTPS backend URL. Only that server address is retained by the client; authentication uses HttpOnly cookies.

The website uses the same Next.js static export. It can be hosted on any HTTPS static host, but this repository does not yet contain a website deployment workflow or hosting infrastructure. Its configured API URL must point to a separately deployed FastAPI backend.

## User experience by role

| Role | Onboarding | Shared corpus | Private case material |
|---|---|---|---|
| Citizen | Self-registration is allowed | Search and chat over the global legal corpus | No professional case workspace by default |
| Police | Administrator provisions the account | Global corpus is always available | Creates and accesses only police cases owned by that user |
| Advocate | Administrator provisions the account | Global corpus is always available | Creates and accesses only advocate cases owned by that user |

A named police or advocate case query searches the global corpus and that role's private vector collection together. Private retrieval fails closed unless a valid `case_id` filter is present, and ownership checks return not-found for another user's case.

## Where data lives

### Global corpus

- Canonical source PDFs, manifests, and rebuild inputs: host filesystem at `data/legal_kb`, bind-mounted into the backend.
- Retrieval chunks and embeddings: Qdrant global collection (`global_legal_corpus_v3` in the current Compose configuration).
- Administrator-staged corpus objects: versioned MinIO corpus bucket.
- The global corpus is rebuildable from the validated source files and manifests and must never be bundled into a public desktop release.

### Personal and case data

- Raw uploaded case documents: versioned MinIO bucket separated by role (`police` or `advocate`) and object keys scoped by owner and case.
- User account, hashed password, role, case metadata, extracted/OCR text, chat sessions, messages, citations, background jobs, and audit records: PostgreSQL.
- Case document chunks and embeddings: role-specific Qdrant collection with mandatory `case_id` filtering.
- Generated exports: separate versioned MinIO generated-output bucket.
- Object namespace, owner, case, and version metadata: PostgreSQL.

PostgreSQL, MinIO, Qdrant, Ollama, and their ports belong on the private data plane. Only the HTTPS API should be reachable by clients.

## Communication path

1. A browser or Tauri client calls the configured FastAPI HTTPS endpoint and sends the HttpOnly session cookie.
2. FastAPI authenticates the user, checks role permissions, and enforces case ownership.
3. Global search queries Qdrant's global collection. A named professional case also queries that role's private collection with a mandatory `case_id` filter.
4. Uploaded files pass through the backend into the correct versioned MinIO bucket. Text/OCR extraction is recorded in PostgreSQL; chunks and embeddings are written to the private Qdrant collection.
5. The RAG graph performs query understanding, retrieval, reasoning, verification, and controlled retry. Model requests go from the private backend to the host's Ollama service, not to a public AI provider.
6. The answer, citations, confidence data, and chat history are stored in PostgreSQL and returned to the client.
7. Large files are transferred through the backend or short-lived presigned URLs; storage credentials are never given to the client.

## Deployment plan

### Phase 0 — release readiness

- Keep `main` green in backend, frontend, correctness, and security CI.
- Set release version, release notes, signing identity, and Tauri updater keys.
- Tag `v*`; let the workflow produce and verify the draft GitHub Release.
- Manually inspect installers, signatures, updater manifest, and release notes before publishing the draft.

### Phase 1 — private pilot

- Use one strong private host for Docker services and Ollama.
- Persist and back up PostgreSQL, MinIO, Qdrant, Ollama models, and `data/legal_kb`.
- Expose only FastAPI through Tailscale Serve or a TLS reverse proxy. Never use public port forwarding or Tailscale Funnel for the pilot.
- Configure real secrets, trusted hosts, CORS origins, secure cookies, and the public HTTPS base URL.
- Create police and advocate accounts administratively; allow citizens to self-register only if the pilot requires them.
- Run restore drills for case files and PostgreSQL before accepting real matters.

### Phase 2 — website release

- Add a deployment workflow for the static `frontend/out` artifact.
- Host the UI behind HTTPS and set its API base URL to the hardened backend.
- Put the API behind TLS ingress/WAF, rate limiting, request-size limits, and monitoring.
- Validate cross-origin cookie behavior, `SameSite`, CORS, trusted hosts, CSRF protections, and logout/refresh flows on the production domains.
- Keep databases and model endpoints private; a public website does not imply a public data plane.

### Phase 3 — production hardening and scale

- Move PostgreSQL, object storage, and vector storage to managed or independently backed-up services.
- Separate API, ingestion/job workers, and model workers so long OCR or deep-review jobs cannot starve interactive traffic.
- Use a secret manager, encrypted storage and backups, audit retention, centralized logs/metrics/traces, alerting, and tested disaster recovery.
- Add tenant-level authorization tests, malware scanning for uploads, data-retention/deletion controls, privacy notices, incident response, and legal review.
- Load-test retrieval, uploads, concurrent model inference, and updater rollout before general availability.

## Recommended launch decision

Use the current architecture for a controlled, private pilot. Do not expose the current single-host Compose stack directly to the public internet. A public website is safe only after the backend ingress, secrets, storage isolation, backup/restore, monitoring, abuse controls, and privacy operations in Phases 2 and 3 are in place.

The interactive, source-linked diagram is `docs/architecture/release-deployment-architecture.html`.
