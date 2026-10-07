# Corpusil — components to show in a system architecture diagram

Everything below exists in the codebase. Counts are real: 15 routers, 12
agents, 28 services, 19 PostgreSQL tables, 3 Qdrant collections.

Draw it as six layers top to bottom, with one vertical band down the right for
the cross-cutting concerns.

---

## 1. Clients

| Component | Note |
|---|---|
| Citizen workspace | Next.js 14 / React 18 |
| Police workspace | same app, role-gated |
| Advocate workspace | same app, role-gated |
| Admin console | corpus and user administration |
| Desktop shell | Tauri wrapper over the same frontend |

One arrow down, labelled **JWT or HTTP-only session cookie**.

## 2. API layer — FastAPI

Show the gateway box, then the 15 routers grouped by what they serve:

- **Conversation**: `chat`, `feedback`
- **Identity**: `auth`, `admin`
- **Case work**: `cases`, `documents`, `investigation`, `authorities`,
  `strategy`
- **Citizen**: `citizen_intake`, `document_analysis`
- **Corpus and platform**: `ingestion`, `retrieval`, `storage`, `jobs`

Inside the gateway box: **JWT + cookie auth**, **RBAC permission guard**,
**per-user rate limiter**, **audit log writer**, **token revocation**.

## 3. Safety and routing — before any retrieval

| Component | What it decides |
|---|---|
| `citizen_safety` | Screens self-harm and emergency queries, returns a helpline response and stops |
| `adaptive_routing` | Fast lane or Deep lane, with no LLM in the routing path |
| `citizen_context` | Selects which uploaded document excerpts are relevant |

Label the router box with the rule that matters: **a citizen on auto always
takes the Deep lane**, because the Fast lane returns source passages rather
than an answer.

## 4. The two lanes

**Fast lane** — one box: `fast_research`. Hybrid retrieval, a minimum
candidate floor, a coverage gate that abstains rather than answer from the
nearest passage, and ranked authority passages with no synthesis.

**Deep lane** — a LangGraph state machine. Draw six nodes in order:

`role_context` → `query_understanding` → `retrieval` → `reasoning` →
`verification` → `response_generation`

With these conditional edges as dashed arrows:

- retrieval → reasoning, *evidence sufficient*
- retrieval → response_generation, *insufficient, refuse rather than answer*
- verification → response_generation, *claims supported*
- verification → retrieval, *unsupported claim, retry, max 2*

Also in this layer, used by the professional roles: `drafting_agent`,
`defence_strategy_agent`, `orchestrator`, `publication`, `prompt_registry`,
`role_profiles`.

## 5. Retrieval and legal-reasoning services

| Component | Role |
|---|---|
| `retrieval` | Hybrid search, Qdrant server-side Reciprocal Rank Fusion |
| BGE-M3 embedder | Dense 1024-d plus sparse lexical vectors |
| `section_mapping` | Concordance: repealed IPC / CrPC / Evidence Act sections to the 2023 Sanhitas |
| `currency` + `repeal_labels` | Marks superseded and repealed sources so they cannot ground a claim |
| `citation_following` | Pulls in provisions a retrieved passage cites |
| `citation_status` | Whether a cited authority is still good law |
| `section_confidence` | Confidence that the right provision was identified |
| `legal_term_normalization` | Corrects "bnss", "ipc" style typos to known acronyms |
| `llm` | Ollama client: qwen3-14b-16k, temperature 0, seeded, concurrency 1 |

## 6. Data and ingestion

**Stores** (draw as cylinders):

- **Qdrant** — `global_legal_corpus_v4` (active), `police_case_data`,
  `advocate_case_data`
- **PostgreSQL 16** — 19 tables. Worth naming on the diagram: `users`,
  `roles`, `permissions`, `cases`, `case_documents`, `chat_sessions`,
  `chat_messages`, `audit_logs`, `jobs`, `corpus_sources`, `corpus_intakes`
- **MinIO** — uploaded case documents and evidence files

**Ingestion pipeline** (a chain feeding Qdrant):

`extract` (PyMuPDF + Tesseract OCR) → `structure` → `chunker` → `classifier` →
`enrichment` → `citations` → `dedup` → `supersession` → `embedder` →
`qdrant_writer`

Plus `validate` and `metadata` beside it as the manifest guards.

**Acquisition** (feeding ingestion, these are the scripts):

`fetch_sources` → `promote_candidates` → canonical manifest → `corpus_health`
and `corpus_reports`. Source: the India Code DSpace API, High Courts, NALSA,
ministries and regulators.

## Cross-cutting band (right-hand side, touching every layer)

- Audit logging
- Role-based access control
- Evidence and currency metadata carried on every chunk
- `pipeline_telemetry` — per-stage timings on every request
- `job_worker` / `jobs` — background work for ingestion and long documents

---

## The three labels that make this diagram worth showing

Most RAG architecture diagrams are interchangeable. These three are what make
yours specific, so do not leave them off:

1. **retrieval → response_generation, "insufficient, refuse rather than
   answer"** — the system abstains instead of answering from the nearest
   passage.
2. **verification → retrieval retry, max 2** — a claim that is not supported
   sends the pipeline back for more evidence.
3. **A note on verification: every published claim must name a chunk that was
   actually retrieved.**
