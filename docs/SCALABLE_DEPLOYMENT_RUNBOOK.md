# Scalable four-user deployment runbook

Updated: **2026-08-28 IST**

## Chosen architecture

The normal product is a lightweight macOS/Windows Tauri client connected to one
private, self-hosted service plane. The global corpus, vector index, databases,
embedding models and LLM are installed once on the server, not downloaded by
every user:

```text
Windows/macOS Tauri clients (small installers)
          |
          | private HTTPS; JWT/RBAC; exact CORS origin
          v
FastAPI + LangGraph service
          +-- PostgreSQL: users, roles, owned cases, chats and audit
          +-- Qdrant: one shared legal collection plus role/case-filtered data
          +-- MinIO: owner/case-namespaced evidence
          +-- BGE-M3 + reranker: shared warm retrieval models
          +-- Ollama now; vLLM/SGLang GPU serving when concurrency grows
```

This is the best current trade-off for a four-person capstone pilot and a later
larger deployment. The desktop stores only the selected backend origin. A move
from the current host to a GPU server requires changing that URL, not
reinstalling the corpus on every computer.

The approximately 954 MiB corpus pack is an operator backup/import artifact.
It is not part of the ordinary client download.

## Data ownership and shared corpus

- `global_legal_corpus` is common, governed and read-only to ordinary roles.
- Citizen requests retrieve only the governed global corpus.
- Police private vectors live in `police_case_data` and every query is filtered
  by an owned `case_id`/uploader scope.
- Advocate private vectors live in `advocate_case_data` with the same mandatory
  owned-matter boundary.
- PostgreSQL ownership and backend permission dependencies are authoritative;
  hiding a frontend route is not treated as security.
- Evidence is stored under role/case/owner-controlled object records. The
  desktop uses authenticated FastAPI upload/download endpoints; database,
  Qdrant, MinIO and Ollama ports are never exposed to clients.
- Admin governs accounts, corpus intake and audit. It is not presented as an
  ordinary Police/Advocate case workspace.

For the current pilot this is application-level multi-tenancy. A larger
high-assurance deployment should add PostgreSQL row-level security, independent
encryption/tenant keys and automated cross-tenant denial tests while retaining
the current backend checks.

## Request logic

1. The user opens Aegis and the Tauri readiness screen probes the saved
   `/health` endpoint and records its latency.
2. Login is sent only to the selected private HTTPS API. FastAPI validates the
   password, account activity and role, then issues short-lived access and
   rotating refresh credentials in HttpOnly cookies.
3. The backend derives permissions and ownership from the authenticated user;
   it does not trust a role/case scope supplied by the UI.
4. Query understanding classifies intent, complexity and whether a professional
   case scope is authorized.
5. Fast mode performs warm BGE hybrid retrieval and returns a cited evidence
   brief without an LLM. Auto uses deterministic signals. Deep adds reranking,
   bounded LangGraph agents and local self-hosted generation.
6. Global evidence is fused with only the authorized private case evidence.
7. The verifier checks claims against retrieved passages, allows at most two
   correction retries, marks partial/unsupported claims and preserves page-level
   provenance.
8. The answer, citations, timings and audit trace are returned. Private data is
   not placed in the shared corpus.

## Four roles

### Citizen

Plain-language legal research and escalation guidance against the shared
corpus. No professional case creation, evidence intake, FIR drafting, defence
workspace or admin controls.

### Police

Owned investigation matters, evidence upload/indexing, selected-case search,
document analysis and grounded FIR drafting. Unknown facts stay explicit and
another officer's case ID must be denied.

### Advocate

Owned client matters, private evidence analysis, two-sided defence research,
counterpoints and evidence/legal-source separation. Fabrication, concealment
and witness coaching are rejected.

### Admin

Police/Advocate account provisioning and suspension, governed global-corpus
staging/validation/publication, immutable Gold protection and audit review.

## Initial four-user setup

### Host computer

1. Use the existing 24 GB Apple Silicon host for the technical pilot. Keep it
   powered, awake and on a stable network.
2. Install/open Docker Desktop, Ollama and Tailscale. Pull
   `qwen3-14b-16k:latest`.
3. Create `.env` from `.env.example` and use strong independent secrets. Never
   commit or send this file.
4. Run:

   ```bash
   ./scripts/start_private_demo_host.sh
   ```

   The script starts the local service plane with secure cross-site cookies,
   waits for warm API readiness, configures private Tailscale Serve HTTPS and
   prints the exact backend URL.
5. Keep FastAPI on `127.0.0.1:8000`. PostgreSQL, Qdrant, MinIO and Ollama are
   loopback-only. Do not use Tailscale Funnel or router port forwarding.

### Each friend

1. Install Tailscale and accept the owner's invite.
2. Download the correct GitHub Release installer:
   - Windows 10/11 x64: `x64-setup.exe`
   - Apple Silicon Mac: `aarch64.dmg`
   - Intel Mac: `x64.dmg`
3. Because this capstone preview has no paid OS publisher certificate, use the
   operating system's explicit **Open anyway** / **More info → Run anyway**
   review after confirming the release filename and SHA-256.
4. Open Aegis → **Private backend connection** → enter the printed
   `https://...ts.net` URL → **Test connection** → **Save & reconnect**.
5. Log in with the role account provisioned by Admin. Friends do not install
   Docker, PostgreSQL, Qdrant, MinIO, BGE models, corpus data or Ollama.

Tailscale account invitation and installing Tailscale on each device are the
remaining unavoidable manual network steps. The app never embeds a Tailscale or
GitHub access token.

## Performance policy

- Keep Fast Research as the default interactive mode. The accepted warm result
  is p95 **448.99 ms** at concurrency one and all five measured queries were
  under five seconds.
- Deep Review is a quality workflow, not a five-second promise. Accepted live
  paths were about 46–47 seconds and one stress path exceeded 180 seconds.
- Keep the embedding and reranker models warm. Cache repeated query embeddings.
- On the 24 GB pilot host start Ollama with one parallel request unless memory
  measurements justify more; extra parallel contexts consume more memory.
- Add streaming and asynchronous Deep jobs before presenting Deep as a smooth
  multi-user interactive feature.

Ollama removes provider token billing and external rate quotas; it does not
create infinite compute. Requests can queue or overload the host. When usage
outgrows the pilot, move inference to a Linux GPU server with vLLM/SGLang,
continuous batching, prefix caching and metrics. Keep the FastAPI inference
adapter stable so clients do not change.

## Scale phases

1. **Four-user pilot:** current Mac + Docker services + Ollama + Tailscale.
2. **Reliable single server:** dedicated Linux/NVIDIA host, UPS, encrypted
   backups, vLLM/SGLang, reverse proxy and monitoring.
3. **Team deployment:** multiple stateless FastAPI workers; managed/replicated
   PostgreSQL, Qdrant and S3; background OCR/ingestion workers; Redis queue;
   streaming; per-tenant quotas and row-level security.
4. **Larger production:** load balancer, autoscaling GPU inference, replicas,
   point-in-time recovery, observability/SLOs, corpus promotion pipeline and
   disaster-recovery exercises.

## Security and acceptance

- Only FastAPI is reachable through private HTTPS.
- Exact origin/host allowlists, secure cookies and origin checks protect cookie
  mutations. Wildcard credentialed CORS is rejected.
- Every private lookup is role + owner + case scoped and audited.
- Validate Citizen/Police/Advocate/Admin boundaries with synthetic data,
  including cross-owner case IDs and malicious Origin/Host requests.
- Back up PostgreSQL, all Qdrant collections and MinIO together; test restore in
  an isolated environment. Never use `docker compose down -v` on retained data.
- This is legal decision support, not legal advice or court-outcome prediction.

## Alternative modes

- **Optional offline pack:** strongest outage/privacy isolation, but duplicates
  roughly 1 GB of corpus plus 6.4 GB of BGE models and an Ollama model on every
  device. Use for disaster recovery or a future air-gapped edition.
- **External LLM API:** smallest infrastructure burden, but introduces provider
  cost, quotas and third-party processing. It is not the default.
- **Local Ollama on every client with central retrieval:** avoids central LLM
  compute but creates inconsistent hardware performance and requires a larger
  orchestration/auth redesign. It is not recommended for this pilot.
