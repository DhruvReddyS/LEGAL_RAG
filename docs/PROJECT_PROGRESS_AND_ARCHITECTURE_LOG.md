# Project progress and architecture log

Last consolidated: **2026-08-29 IST**

## Purpose and evidence policy

This is the durable engineering ledger for the Multi-Agent Legal RAG platform.
It separates implemented and tested behavior from targets and proposals. The
scope-frozen feature specification remains the product source of truth;
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) is the ordered delivery plan.
Detailed acceptance records linked below are authoritative for their measured
runs. Test totals are snapshots of an evolving suite and must not be added
together.

## Executive status

| Phase | State | Accepted scope | Important remaining work |
| --- | --- | --- | --- |
| P0 / Tier 0 | Complete | Monorepo, Compose, async SQLAlchemy/Alembic, PostgreSQL, Qdrant, MinIO, JWT/RBAC, ownership and audit foundations | Production secret rotation/operations remain deployment duties |
| P1 / Tier 1 | Complete | OCR ingestion, BGE-M3 dense+sparse vectors, hybrid retrieval/reranking, LangGraph verification, chat API, citizen UI and Tauri shell | None for the accepted MVP definition |
| P2 / Tier 2 | Partial, substantial | Case workspaces, isolated evidence, FIR/defence workflows, role consoles, Fast/Auto RAG, admin governance, Document Analyzer and Evidence Inspector | Document Studio/export, judgment tools, amendment tracker, feedback, durable jobs and streaming |
| Deep performance | Not accepted | Functional local Deep flows and a 46.25-second analyzer run exist | General synchronous 14B Deep exceeded 180 seconds under stress |
| P3–P7 | Pending | Plan only | Case intelligence, courtroom, academic evaluation, multilingual/voice and other stretch work |
| Desktop distribution | Public capstone preview released | Tauri v2 clients for macOS arm64, macOS x64 and Windows x64; signed updater artifacts; public v0.3.0 release | OS publisher signing/notarization and clean-machine friend validation |
| Four-user scalable release | Software/release complete; network onboarding pending | Runtime-selectable private backend, loopback hardening, shared-host launcher and public three-target release | Install/invite through Tailscale and run clean Windows/Mac acceptance |

## Current implemented architecture

```text
Next.js 14 static UI inside Tauri v2
        |
        | HttpOnly cookie auth / REST
        v
FastAPI + Pydantic v2
        |
        +-- JWT access/refresh, RBAC, ownership, audit -> PostgreSQL
        +-- evidence/corpus objects                   -> MinIO (S3 API)
        +-- dense+sparse retrieval and payloads       -> Qdrant
        +-- BGE-M3 embedding + BGE reranking          -> local model cache
        +-- bounded LangGraph Deep workflow           -> local Ollama
```

The desktop UI does not call Ollama directly. FastAPI is the only orchestration
boundary. Fast Research can operate without Ollama; Deep Review requires it.
The accepted local developer deployment runs FastAPI and data services through
Compose while native Ollama runs on the host.

## How the system works

### Infrastructure and data isolation

- PostgreSQL stores application identity, sessions, cases, chats, generated
  records and audit state through SQLAlchemy 2.0 async models and Alembic.
- Qdrant uses three named collections:
  `global_legal_corpus`, `police_case_data`, and `advocate_case_data`.
  They have dense and sparse vector support plus indexed payload fields.
- MinIO provides the S3-compatible boundary for corpus and uploaded evidence.
- Case ownership is enforced in backend dependencies, not merely hidden in the
  frontend. Police and advocate evidence is retrieved from the role-specific
  collection and scoped to owned cases.
- JWT access and refresh tokens, bcrypt password hashing, inactive-user checks,
  role permissions and audit traces form the application security boundary.
  HttpOnly cookies prevent frontend JavaScript from storing bearer tokens.

### Corpus ingestion

1. Canonicalize source documents and maintain one cache/manifest per canonical
   document.
2. Extract native PDF text with PyMuPDF when viable; use Tesseract OCR fallback
   for scanned pages.
3. Split text into source-addressable chunks with page and document metadata.
4. Produce BGE-M3 dense and learned sparse representations.
5. Upsert vectors and payloads into `global_legal_corpus`.
6. Run strict count/cache validation and a 12-query legal retrieval smoke suite.

The accepted Gold build contains 381 canonical documents. The 419 physical PDF
count includes duplicates/physical inputs and must not be presented as 419
unique canonical authorities. Candidate files under `data/source_materials`
are not automatically Gold; provenance and quality governance is required.

### Retrieval and grounding

- Hybrid search combines dense semantic and learned sparse candidates in
  Qdrant using reciprocal-rank fusion.
- Deep mode applies the BGE reranker and the LangGraph reasoning/verification
  workflow. The workflow performs query understanding, retrieval, cited
  reasoning, claim verification and no more than two correction retries.
- Claims are tied to source markers and evidence states. The verifier can mark
  support as yes, partial or no; unsupported claims are corrected or surfaced
  as insufficient evidence rather than silently asserted.
- Citations retain document/page/chunk provenance. The Evidence Inspector adds
  the accepted seven-field source view for human review.
- Private document analysis uses owned, indexed chunks and cross-checks proposed
  legal sections against the corpus; an invented-section live test was rejected.

### Fast, Auto and Deep execution

| Mode | Mechanism | Accepted behavior |
| --- | --- | --- |
| Fast Research | Warm BGE retrieval, embedding cache, no reranker and no LLM generation | Evidence brief or explicit abstention with stage timings; p95 448.99 ms at concurrency 1 |
| Auto | Deterministic, auditable complexity signals | Focused questions route Fast; complex or case-scoped work routes Deep; an explicit user choice is not overridden |
| Deep Review | Hybrid retrieval, reranking and bounded multi-agent verification through local Ollama | Functionally grounded, but general interactive latency is not accepted |

The deterministic Auto router avoids adding an LLM routing call. Separate
concurrency controls keep a Deep rerank from monopolizing Fast retrieval; the
recorded Fast request during Deep reranking completed in 915.6 ms. Fast's
five-second result is a retrieval/evidence result, not a generated legal essay.

### Role-specific product surfaces

- **Citizen:** general legal guidance, grounded corpus research and safe
  escalation without access to professional case resources.
- **Police:** owned case workspace, evidence upload/indexing, analysis and
  immutable grounded FIR drafting with unknown fields left explicit.
- **Advocate:** owned case workspace, two-sided defence analysis, scenario/legal
  source separation, counterpoints and unsafe-tactic rejection.
- **Admin:** professional account creation/suspension, governed corpus
  staging/validation/publication, audit review and immutable Gold protection.

These are distinct command centres, navigation structures, agent suites,
workflows and shortcuts. Backend authorization remains decisive even if a route
or control is absent from a role's UI.

### Document Analyzer and Evidence Inspector

The accepted analyzer endpoint is
`POST /documents/analyze?case_id={owned-case-id}`. Police and advocate users may
analyze owned indexed evidence; a citizen is denied and an admin retains the
governance boundary. Analysis returns chunk-grounded clauses/risks and corpus
validation rather than accepting invented authority. The frontend source
drawer exposes the seven accepted provenance fields. See
[DOCUMENT_ANALYZER_ACCEPTANCE.md](DOCUMENT_ANALYZER_ACCEPTANCE.md) for the
contract, permissions and live fictional-document run.

## Delivery history by plan phase

### Tier 0 / P0 — core infrastructure

Completed in plan order:

1. Exact monorepo and FastAPI health scaffold.
2. Compose services, health checks, named volumes, backend image and optional
   Ollama profile; host Ollama connectivity was also verified.
3. Async SQLAlchemy models and reversible Alembic migration setup.
4. Three isolated Qdrant collections with dense/sparse vectors and payload
   indexes.
5. JWT access/refresh auth, bcrypt, seeded RBAC and ownership dependencies.
6. MinIO storage boundary, audit logs, migrations, health and integration tests.

### Tier 1 / P1 — verified RAG MVP

- Ingested and strictly validated the Gold corpus.
- Accepted BGE-M3 hybrid retrieval, BGE reranking and 12/12 smoke questions.
- Added bounded LangGraph reasoning/verification, citations, confidence,
  PostgreSQL sessions/memory, ownership and traces.
- Delivered the citizen Next.js static frontend with secure cookie auth.
- Packaged and exercised the Tauri v2 Apple Silicon desktop shell.

The accepted end-to-end FIR query produced two verified page citations at
confidence 0.625 in 47.18 seconds. This is a Deep workflow result and is not the
Fast-mode latency claim.

### Tier 2 / P2 — professional core delivered so far

- Police/advocate case CRUD and dependency-enforced ownership.
- S3 evidence upload plus PDF/text extraction and OCR fallback.
- Role-specific private Qdrant indexing and selected/all-owned-case search.
- Immutable grounded FIR drafting and verified two-sided defence analysis.
- Professional role operating systems and case-aware Deep retrieval.
- Fast Research plus deterministic Adaptive Corrective Hybrid RAG.
- Admin account and corpus governance control plane.
- Adversarial retrieval/privacy/hallucination stress checks.
- Document Analyzer and Source Provenance/Evidence Inspector.

P2 is not complete as a whole. Its remaining scope is listed in the backlog.

## Quantities and performance evidence

### Corpus and ingestion

| Metric | Accepted value |
| --- | ---: |
| Physical PDF inputs | 419 |
| Canonical documents | 381 |
| Pages | 17,426 |
| Native-text pages | 13,448 (77.17%) |
| OCR pages | 3,978 (22.83%) |
| Chunks / BGE embeddings / Gold Qdrant points | 25,517 each |
| Valid document caches | 381 / 381 |
| Failed documents / validation issues | 0 / 0 |
| Average chunks per canonical document | 66.97 |
| Chunk word count p90 / p95 / max | 700 / 700 / 700 |
| Retrieval smoke suite | 12 / 12 passed |
| Observed wall-clock ingestion envelope | 22 h 50 m 26 s, including stops/retries |
| Optimized Apple MPS embedding sample | 505 chunks / 193.48 s = 156.6 chunks/min |
| Estimated active embedding time at that measured rate | approximately 2 h 43 m |

The wall-clock envelope is not pure compute time. The active embedding estimate
is derived from the measured optimized sample and should be re-measured on each
target machine. Full methodology is in
[INGESTION_ASSESSMENT.md](INGESTION_ASSESSMENT.md).

### Query and analysis latency

| Measurement | Result | Qualification |
| --- | ---: | --- |
| First recorded authenticated warm Fast query | 412.54 ms | Four citations |
| Five-query warm Fast mean | 343.76 ms | Concurrency 1 |
| Five-query warm Fast p95 | 448.99 ms | 100% under 5 seconds, concurrency 1 |
| Recorded Fast range in stress suite | 18.97–2,908.68 ms | Includes varied adversarial paths |
| Fast while Deep was reranking | 915.6 ms | Separate workload controls |
| Accepted warm FIR Deep workflow | 47.18 s | Two verified citations |
| Live Document Analyzer Deep run | 46.25 s | Fictional TXT, one private page/chunk |
| General current-law Deep stress case | over 180 s | Timed out; not accepted |

Claim/citation parsing changes reduced an accepted query's latency by 74.3% in
the recorded ingestion/performance assessment. Do not generalize that single
comparison into a universal speedup. See
[FAST_MODE_ACCEPTANCE.md](FAST_MODE_ACCEPTANCE.md) and
[RAG_STRESS_TEST_REPORT.md](RAG_STRESS_TEST_REPORT.md).

### Capacity projection

The measured corpus average is about 67 chunks per canonical document and about
1.6 MiB of PDF input per document. A simple linear planning estimate for 1,000
additional similarly shaped documents is about 67,000 chunks and 1.6 GiB of
PDFs, before vector/index overhead. This is capacity planning, not a measured
future ingestion run. Details and scaling gates are in
[PERFORMANCE_AND_CORPUS_SCALING_PLAN.md](PERFORMANCE_AND_CORPUS_SCALING_PLAN.md).

## Verification record

| Acceptance record | Evidence snapshot |
| --- | --- |
| Current consolidated backend regression | 116 tests passed; Next static build/lint/type-check passed |
| Document Analyzer | 8 focused tests, 105 full tests, Next/Tauri build, live fictional TXT analysis |
| Role operating system | 16 focused tests, 101 full tests, Next build and browser QA |
| Adaptive RAG | 9 focused tests; 78 passed plus one unrelated MinIO environment failure in that earlier snapshot; Next build passed |
| Fast mode | 9 focused tests, 80-test full snapshot, Next build and browser QA |
| Tier 2 first vertical slice | 72-test snapshot plus live scenario checks |
| Admin control plane | 2 focused tests, 101 tests in 13.32 s, Next build and live Gold validation |

The current consolidated number is 116, not the sum of rows. Earlier lower
totals record when a feature was accepted. Commands for the current suite and
strict corpus validation are in [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md).

## Desktop and release status

- Current public product version: **v0.3.0**, published as the latest regular
  GitHub Release on **2026-08-28 09:48:59 UTC**:
  <https://github.com/DhruvReddyS/LEGAL_RAG/releases/tag/v0.3.0>.
- The release points to commit `3724e23` and contains nine audited assets:
  Apple Silicon DMG/updater archive/signature, Intel Mac DMG/updater
  archive/signature, Windows x64 NSIS installer/signature, and `latest.json`.
- Installer sizes are 5,314,210 bytes for the Apple Silicon DMG, 5,582,862
  bytes for the Intel DMG and 3,567,106 bytes for the Windows installer. The
  ordinary client therefore remains a small download and does not include the
  approximately 954 MiB optional corpus pack or the Ollama model.
- The published `latest.json` reports version `0.3.0`, six signed platform keys
  (`darwin-aarch64`, `darwin-aarch64-app`, `darwin-x86_64`,
  `darwin-x86_64-app`, `windows-x86_64`, and `windows-x86_64-nsis`). Anonymous
  requests to the public manifest and ranged installer/updater downloads were
  accepted after publication.
- Clean GitHub CI timings were: validation 4 m 8 s, Apple Silicon build 5 m
  17 s, Windows x64 build 9 m 0 s and Intel Mac build 19 m 35 s. All jobs and
  the draft-asset verification job passed.
- Both downloaded macOS `.app` updater archives passed
  `codesign --verify --deep --strict`; the Windows download was identified as a
  PE32 GUI x64-compatible NSIS self-extracting installer. Downloaded SHA-256
  values matched the digests recorded by GitHub for all nine assets.
- Accepted local Apple Silicon output: 9.6 MB `.app`, 2.8 MB `.dmg`, macOS 11+
  target metadata and strict local ad-hoc signature verification.
- Toolchain recorded in acceptance: Tauri CLI 2.11.4, Rust Tauri 2.11.5,
  Rust/Cargo 1.98.0.
- The release CI ran the 116-test backend suite, Alembic migrations, MinIO/S3
  initialization, frontend lint/static export and all three native builds in a
  clean hosted environment.
- `.github/workflows/release.yml` and the release helper scripts form the GitHub
  Release/updater foundation. Version tags and secrets are validated before the
  workflow creates a draft; publication remains a deliberate post-audit step.

This is still a preview distribution, not a trusted offline product installer:

- the local macOS signature is ad-hoc; external distribution needs Developer ID
  signing and Apple notarization;
- Windows updater signatures do not supply a trusted Authenticode publisher;
- clean-machine Windows execution remains a release gate;
- the package contains UI/native shell, not the backend, databases, corpus,
  embedding models or Ollama;
- v0.3.0 is public so its manifest and updater assets are anonymously
  retrievable; never embed a GitHub token in the desktop application.

See [TAURI_DESKTOP_ACCEPTANCE.md](TAURI_DESKTOP_ACCEPTANCE.md),
[GITHUB_RELEASES.md](GITHUB_RELEASES.md), and
[FOUR_USER_RELEASE_RUNBOOK.md](FOUR_USER_RELEASE_RUNBOOK.md).

## Chosen scalable four-user architecture

The selected normal deployment is a lightweight Tauri client connected through
private HTTPS to one self-hosted service plane. PostgreSQL, Qdrant, MinIO, BGE
models, the corpus and Ollama are installed once on the server. Each user's
private records remain owner/role/case scoped in the shared services; the global
corpus is common. The runtime backend URL can be changed in the desktop app, so
moving from the current Mac to a Linux/GPU host does not require rebuilding the
clients. See [SCALABLE_DEPLOYMENT_RUNBOOK.md](SCALABLE_DEPLOYMENT_RUNBOOK.md).

The backend now validates exact CORS origins/trusted hosts, rejects unsafe
credentialed-origin mutations, requires secure cookies for cross-site HTTPS and
binds PostgreSQL, Qdrant, MinIO and container Ollama to loopback. The current
expanded backend regression is **116 tests passed**. The desktop now tests,
measures and safely stores a runtime private backend origin; remote mode does
not require friends to install local Docker/Ollama/corpus services.

## Optional offline/private architecture

An optional air-gapped target is one complete independent stack per computer:

```text
signed Tauri application
  -> loopback-only FastAPI managed sidecar/service
       -> device-local PostgreSQL
       -> device-local Qdrant (three collections)
       -> device-local MinIO/object storage
       -> device-local BGE models/cache
       -> device-local Ollama + approved model
       -> signed/versioned legal corpus pack
```

Design consequences:

- Ordinary use works with the network disabled; there is no central availability
  dependency and private cases do not traverse a LAN or cloud service.
- Every device duplicates model/corpus/index storage and must be benchmarked,
  updated, backed up and restored independently.
- There is no current cross-device case, account, admin or corpus sync. An admin
  on one computer does not control the other installations.
- Local RBAC still matters. Physical isolation does not justify disabling role
  checks, case ownership or auditing.
- Application, backend, schema, model and corpus versions need a visible
  compatibility contract. Updates must be signed, checksummed and reversible.
- A future corpus pack should be staged and validated before promotion, with a
  manifest/checksums and a rollback-safe Qdrant migration. This is planned, not
  yet implemented.

The implemented corpus-pack builder now produces a checksum-addressed public
pack containing the 419 physical PDFs, metadata and a pre-indexed
`global_legal_corpus` Qdrant snapshot. The measured complete pack is
1,000,570,880 bytes (about 954 MiB), contains 381 canonical documents, 17,426
pages and 25,517 points, and explicitly excludes accounts, cases, private
vectors, evidence and secrets. This is retained as backup/air-gapped groundwork,
not the ordinary scalable-client download.

## Manual operations currently required

### Start the scalable four-user private host

The remaining deployment blocker on the accepted host is Tailscale installation
and interactive sign-in. Ollama is installed and the required
`qwen3-14b-16k:latest` model is already present. After the owner installs
Tailscale, signs in and invites the three friends, run:

```bash
./scripts/start_private_demo_host.sh
```

The launcher verifies Docker, Ollama, Tailscale, `.env` and the selected model;
starts the production Compose stack with secure cross-site cookies and exact
trusted hosts; waits for `/health`; enables private Tailscale Serve HTTPS; and
prints the backend URL to save in each desktop client. Friends install only
Tailscale and the correct v0.3.0 desktop installer. They do not install the
corpus, Docker, PostgreSQL, Qdrant, MinIO, BGE models or Ollama.

### Start and check the accepted local developer stack

```bash
docker compose --env-file .env -f docker/docker-compose.yml up -d --build
docker compose --env-file .env -f docker/docker-compose.yml ps
curl --fail http://localhost:8000/health
ollama list
```

The configured model on the accepted machine is
`qwen3-14b-16k:latest`. For the local native path:

```bash
./scripts/start_desktop.sh
```

That launcher is macOS-specific. It is not evidence of Windows offline
bootstrap. Demo usernames/passwords and role walkthroughs are intentionally
kept in [LOCAL_DEMO_USER_MANUAL.md](LOCAL_DEMO_USER_MANUAL.md), not duplicated
in this engineering ledger.

### Secrets

Create `.env` from `.env.example` only on a fresh setup. Manually provide strong
independent PostgreSQL, JWT access/refresh and S3 credentials. Never commit or
print `.env`. For offline four-device deployment, generate different secrets on
each computer.

Release automation additionally needs the Tauri updater public/private key
material and OS signing identities. Keep private signing keys only in protected
CI secrets or an appropriate signing service. Apple notarization credentials
and a Windows Authenticode solution remain external manual prerequisites.

### Validation before using real data

1. Run the complete backend regression and frontend production build using the
   environment-safe commands in [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md).
2. Run strict corpus validation and expect 381 valid caches and 25,517 Gold
   points with zero issues.
3. Run the 12-query retrieval smoke suite.
4. Exercise each applicable role with synthetic cases, including a cross-owner
   case-ID denial and citizen/admin boundary checks.
5. Run warmed Fast queries and record median/p95 on the actual device.
6. Verify a coordinated encrypted backup by restoring it into an isolated
   environment. Never test by overwriting live volumes and never use
   `docker compose down -v` on data that must survive.

## Known limitations and release risks

1. Deep Review is functionally useful but not interactively bounded; one stress
   path exceeded 180 seconds.
2. All 25,517 Gold payloads conservatively have `is_current=false` pending
   official consolidation review. The system must not claim current-law
   certification.
3. The desktop bundle is intentionally a lightweight client; its shared backend
   must remain online for normal scalable operation.
4. Tailscale installation/invitation and clean Windows/macOS friend acceptance
   remain manual deployment/acceptance gates; public release publication itself
   is complete.
5. External macOS/Windows OS trust signing is incomplete.
6. The Next.js 14 dependency line has two high-severity audit findings through
   Next/PostCSS recorded in desktop acceptance. Static export limits server-side
   exposure, but migration to a patched supported major remains backlog.
7. Synchronous OCR/analysis/export work needs durable jobs, cancellation,
   progress and recovery.
8. Legal-corpus growth is governed. Ten candidate source files require review;
   seven are exact Gold duplicates and must not be bulk-promoted.
9. This is legal decision support, not legal advice or judgment prediction.

## Ordered backlog

### A. Scalable pilot and release safety

1. Install/configure Tailscale on the host and three friend devices; allow only
   the private HTTPS API port.
2. Run clean Windows/macOS installer, login, role-isolation and latency checks.
3. Change the four shared demo passwords before any real/confidential material
   is used and verify account suspension/recovery from the Admin console.
4. Add streaming/asynchronous Deep execution and benchmark four-user load.
5. Move Ollama to vLLM/SGLang on a dedicated GPU host when concurrency requires
   continuous batching; keep the inference adapter/client contract stable.
6. Add coordinated encrypted backup/restore, monitoring and host availability
   controls.
7. Retain the offline corpus pack as disaster-recovery/air-gapped groundwork.

### B. Finish Tier 2

1. Legal Document Studio editing, versioning and PDF/DOCX export.
2. Judgment summarizer and judgment similarity mode.
3. Amendment/current-law tracker and an honest outdated-law demonstration.
4. Feedback API/UI and admin quality dashboard.
5. Durable analysis/OCR/export jobs with cancellation and recovery.
6. SSE token, progress and agent-trace streaming.
7. Bound Deep work asynchronously and measure first-token/end-to-end latency,
   concurrency, memory and resource isolation.

### C. Later planned phases

- P3: timelines, evidence maps, missing-information detection, statement
  contradiction analysis and provenance-aware case graph.
- P4: investigation checklist, strategy engine, argument–precedent mapping and
  bounded multi-pass research.
- P5: virtual courtroom/debate report and interactive cross-examination without
  presenting judgment prediction.
- P6: 50–100-item golden evaluation set and vector-only/hybrid/reranker/full-RAG
  ablations with retrieval, citation, hallucination and latency metrics.
- P7: multilingual, voice, enhanced PII anonymization and trace visualization
  only after the prior acceptance gates.

## Current release claim and next acceptance gate

v0.3.0 is honestly described as a **public scalable four-user capstone
preview**: the three desktop targets are published, can select/test a private
backend at runtime, use backend-enforced role/owner isolation, and have signed
automatic-update artifacts. It is not an offline, high-availability or
OS-trusted production distribution claim.

The next acceptance gate is operational rather than another code claim:
Tailscale onboarding, clean-machine installation on the friends' actual Windows
and macOS devices, private HTTPS login for all four roles, cross-owner denial,
Fast-mode latency measurement, restart behavior and an updater rehearsal. OS
publisher trust remains an explicit warning until paid signing/notarization is
added.

## Pending work and how it will be completed

This section is the executable roadmap from the current v0.3.0 baseline. Items
are ordered by dependency and risk. A later feature must not be described as
complete merely because its UI exists; its backend authorization, persistence,
grounding, tests and acceptance evidence must also pass.

### 1. Activate the four-user private pilot

**Pending:** Tailscale is not installed on the accepted host, and the release
has not yet been exercised on the three friends' clean computers.

**How:**

1. The owner installs Tailscale on the host Mac, signs in and invites the three
   friends. Each friend installs Tailscale and accepts the invitation. This is
   an unavoidable interactive/manual identity step; no access token will be
   embedded in Aegis.
2. From the repository root, the owner runs:

   ```bash
   ./scripts/start_private_demo_host.sh
   ```

3. The launcher validates `.env`, Docker, Ollama, the selected model and
   Tailscale; starts the production service plane; configures private HTTPS;
   and prints the `https://...ts.net` backend origin.
4. Friends download v0.3.0 from the official release, install the correct
   Windows/Apple Silicon/Intel package, enter that private origin under
   **Private backend connection**, test it and save it.
5. Run one Citizen, Police, Advocate and Admin session concurrently. Confirm
   login, logout/refresh, role-specific navigation, case ownership denial and
   global-corpus access.

**Acceptance evidence:** all four clients receive a healthy API response over
private HTTPS; each account receives only its role interface; a Police or
Advocate account cannot open another owner's case; Citizen cannot access
professional routes; Admin governance works; no database/vector/object/LLM port
is reachable from a friend device.

**Owner/manual responsibility:** Tailscale installation/sign-in/invitations,
OS warning approval and access to the friends' physical computers. The code,
launcher and release artifacts are already prepared.

### 2. Replace demonstration credentials and establish operations

**Pending:** the four published walkthrough credentials are suitable only for
synthetic capstone testing. Coordinated backup, restore and host monitoring have
not completed acceptance.

**How:**

1. Use Admin to replace or retire the demo professional accounts, create named
   pilot accounts and use unique high-entropy passwords. Rotate `.env` JWT,
   PostgreSQL and S3 secrets if they have ever been shared.
2. Keep `.env`, updater private keys and real evidence outside Git. Never send
   them to friends or place them in a desktop build.
3. Add versioned encrypted backups for PostgreSQL, Qdrant snapshots and MinIO,
   plus a small manifest recording schema, corpus and application versions.
4. Restore the backup into an isolated temporary environment and run health,
   count, ownership and retrieval checks before calling the backup accepted.
5. Add host uptime/disk/RAM/model-queue monitoring and a documented recovery
   procedure. Keep the host awake and Docker, Ollama and Tailscale available
   during the pilot.

**Acceptance evidence:** successful isolated restore, 381 valid Gold caches,
25,517 global points, login for active accounts, denial for suspended accounts,
and zero private objects/vectors exposed across owners.

### 3. Complete clean-machine release and updater acceptance

**Pending:** CI built and audited all three platforms, but installation on the
friends' actual clean Windows/macOS devices and a real automatic-update cycle
remain unverified.

**How:**

1. Install v0.3.0 on Windows x64, Apple Silicon macOS and Intel macOS as
   applicable. Record OS version, architecture, installation time, first-launch
   behavior and any OS warning.
2. Verify connection selection survives restart and that logout clears the
   authenticated session.
3. Publish a harmless signed patch release after validation, then exercise the
   in-app updater from v0.3.0. Verify signature acceptance, restart and retained
   backend configuration.
4. Record installer SHA-256, update duration and failure/recovery behavior in a
   release acceptance document.

**Acceptance evidence:** clean install, launch, authentication, role isolation,
restart and signed update pass on every represented OS/architecture. Paid Apple
notarization and Windows Authenticode remain optional future trust improvements,
not hidden claims of the unsigned capstone preview.

### 4. Make Deep workflows responsive and concurrency-safe

**Pending:** Fast Research meets the current interactive target, but Deep Review
is synchronous and has recorded approximately 46–47 second accepted paths plus
one stress timeout beyond 180 seconds.

**How:**

1. Move OCR, ingestion, analyzer, export and Deep workflows into durable jobs
   with queued/running/succeeded/failed/cancelled states, progress checkpoints,
   retry limits and idempotency keys.
2. Add SSE streaming for job progress, agent stages, citations and generated
   tokens. Preserve the current synchronous contract during migration where
   compatibility requires it.
3. Apply separate Fast/Deep concurrency pools, bounded Ollama queueing,
   cancellation and per-user rate limits so a long Deep task cannot block Fast
   retrieval.
4. Benchmark four simultaneous users and record queue time, time to first
   token, end-to-end latency, tokens/second, embedding/reranker time, CPU/GPU,
   memory, failures and cancellation time.
5. Keep Ollama for the four-person pilot. Move the inference adapter to
   vLLM/SGLang on a Linux GPU host only when measurements show sustained
   concurrency requires continuous batching.

**Acceptance evidence:** Fast p95 remains below five seconds under the agreed
four-user workload; Deep returns visible progress quickly, can be cancelled,
survives client reconnect and no longer holds an HTTP request indefinitely.

### 5. Finish the remaining Tier 2 product scope

Implementation will continue in this dependency order:

1. **Durable jobs and streaming foundation** described above, because document
   generation and analysis depend on it.
2. **Legal Document Studio:** template-backed drafting, explicit unknown fields,
   version history, source links and PDF/DOCX export. Generated text must remain
   editable and traceable to evidence.
3. **Judgment summarizer:** issues, facts, arguments, holdings and cited passages
   with abstention when a component is unavailable.
4. **Judgment similarity:** hybrid retrieval plus reranking, visible comparison
   dimensions and no judgment-outcome prediction claim.
5. **Amendment/current-law tracker:** versioned authority records, effective
   dates, supersession links and an explicit outdated-law demonstration. Until
   then all Gold payloads continue to carry the conservative
   `is_current=false` qualification.
6. **Feedback and quality dashboard:** answer/citation feedback, retrieval and
   verifier diagnostics, role-safe admin aggregation and no exposure of private
   case text.

**Acceptance evidence for every feature:** migration downgrade/upgrade,
permission matrix tests, owner-isolation tests, API contract tests, frontend
production build, synthetic live scenario, citation/abstention checks and a
written acceptance record with timings.

### 6. Harden multi-tenancy and application security

**Pending:** backend ownership/RBAC checks are implemented, but a larger
deployment needs defence in depth beyond application-level multi-tenancy.

**How:**

1. Add PostgreSQL row-level security for tenant/owner-sensitive tables while
   retaining backend authorization dependencies.
2. Add automated cross-tenant denial tests covering guessed IDs, filters,
   exports, object keys, vector payloads, chats, audit data and suspended users.
3. Add tenant/role/owner assertions to all Qdrant private queries and storage
   paths; reject missing scope rather than defaulting to broad search.
4. Add per-tenant encryption-key and retention design before onboarding real
   institutions.
5. Upgrade the recorded Next.js/PostCSS dependency findings to patched supported
   versions, rebuild the static export and rerun the complete desktop matrix.
6. Add dependency/container scanning, secret scanning and a documented security
   response process to CI.

**Acceptance evidence:** zero successful cross-owner accesses in the adversarial
suite, clean dependency/security gates at the agreed severity threshold, exact
CORS/trusted-host checks and no secret/private data inside release artifacts.

### 7. Grow and govern the global legal corpus

**Pending:** additional authorities are desirable, but candidate documents
cannot be bulk-added merely to increase the count. Seven of the current ten
candidates are exact Gold duplicates.

**How:**

1. Prefer primary official sources and record source URL, jurisdiction,
   authority type, dates, checksum, license/provenance and reviewer decision.
2. Stage files outside Gold, run duplicate detection, extraction/OCR quality,
   page mapping, chunk validation and retrieval evaluation.
3. Embed only accepted canonical documents, stage Qdrant changes in a new
   snapshot/collection version and compare the 12-query suite plus new
   domain-specific questions.
4. Publish only after count reconciliation, zero validation issues, regression
   review and rollback snapshot creation.
5. Record physical files, canonical documents, pages, OCR ratio, chunks,
   embedding time/rate, index size, ingestion cost, retrieval quality and failed
   sources for every corpus version.

**Acceptance evidence:** provenance-complete manifest, no unreviewed duplicates,
all caches/points reconciled, retrieval quality non-regressing and a tested
rollback path. Admin corpus publication remains governed and immutable Gold is
never silently overwritten.

### 8. Implement later phases only after the earlier gates

- **P3 case intelligence:** timelines, evidence maps, missing-information
  detection, contradiction analysis and provenance-aware case graph.
- **P4 professional strategy:** investigation checklist, strategy engine,
  argument–precedent mapping and bounded multi-pass research.
- **P5 courtroom simulation:** structured debate and cross-examination practice
  with safety boundaries and no judgment prediction.
- **P6 academic evaluation:** a 50–100-item golden set and vector-only, hybrid,
  reranked and full-RAG ablations measuring retrieval, citations,
  hallucinations, latency and resources.
- **P7 stretch:** multilingual interfaces/retrieval, voice, enhanced PII
  anonymization and trace visualization.

Each phase will be implemented vertically: schema/storage first, backend
authorization and domain logic second, RAG/agent behavior third, role-specific
UI fourth, automated tests fifth, live synthetic acceptance sixth and progress
ledger update last.

### 9. Immediate next sequence

The shortest safe path from today is:

1. **User/manual:** install Tailscale, invite the three friends and run the host
   launcher.
2. **Joint acceptance:** install v0.3.0 on their computers and complete the
   four-role/cross-owner/Fast-latency checklist using synthetic information.
3. **Engineering:** implement durable jobs plus SSE streaming and four-user load
   instrumentation.
4. **Engineering:** complete Document Studio/export, then the remaining Tier 2
   features in the order above.
5. **Operations/security:** establish tested backups, monitoring, credential
   rotation, dependency upgrades and deeper tenant isolation before real data.
6. **Scaling:** move inference from the pilot Mac/Ollama host only when measured
   concurrency justifies a dedicated Linux GPU serving layer.

The next action currently requiring the user is step 1: Tailscale installation,
interactive sign-in and friend invitations. All subsequent code changes can be
implemented and tested incrementally from the current clean v0.3.0 baseline.
