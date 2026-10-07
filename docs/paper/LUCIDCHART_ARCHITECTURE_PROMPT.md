# Lucidchart prompt — Corpusil system architecture

Paste the block below into Lucidchart's AI diagram generator
(**Lucidchart → Create → AI Diagram**, or the Lucid AI panel in an open
document). If your browser extension has a "generate diagram from text" box,
paste the same block there.

---

Create a layered system architecture diagram titled "Corpusil — Multi-Agent
Legal RAG Platform". Use left-to-right flow with six horizontal swimlanes,
rounded rectangles for services, cylinders for data stores, and hexagons for
the agent nodes. Label every arrow with what travels along it.

LANE 1 — CLIENTS
- "Citizen Web App" (Next.js 14, React 18)
- "Police Workspace" (same app, role-gated)
- "Advocate Workspace" (same app, role-gated)
- "Admin Console"
- "Desktop Shell (Tauri)"
All five connect to the API Gateway over HTTPS with a JWT or an HTTP-only
session cookie.

LANE 2 — API LAYER (FastAPI)
- "API Gateway" box containing: "15 Routers", "JWT + Cookie Auth",
  "RBAC Permission Guard", "Per-User Rate Limiter", "Audit Log Writer"
- Arrow from Clients to API Gateway labelled "query, documents, case actions"

LANE 3 — ROUTING AND SAFETY
- "Citizen Safety Screen" (blocks self-harm and emergency queries, returns a
  helpline response before any retrieval)
- "Adaptive Router" — decides Fast lane or Deep lane without calling an LLM.
  Inputs: user role, query text, case scope, conversation history.
  Rule to show on the box: "Citizen on auto always takes the Deep lane,
  because the Fast lane returns source passages and not an answer."
- Two labelled arrows leaving the router: "Fast lane" and "Deep lane"

LANE 4 — THE TWO LANES
Fast lane (single box): "Fast Research — hybrid retrieval, minimum 20
candidates, returns ranked authority passages, no synthesis".

Deep lane: a LangGraph state machine drawn as connected hexagons in order:
  "Role Context" → "Query Understanding" → "Retrieval" → "Reasoning" →
  "Verification" → "Response Generation"
Add these conditional edges, drawn as dashed arrows with labels:
  - Retrieval → Reasoning, labelled "evidence sufficient"
  - Retrieval → Response Generation, labelled "insufficient — refuse rather
    than answer"
  - Verification → Response Generation, labelled "claims supported"
  - Verification → Retrieval, labelled "unsupported claim — retry, max 2"
Attach a note to Verification: "Every published claim must name a chunk that
was actually retrieved."

LANE 5 — RETRIEVAL AND REASONING SERVICES
- "BGE-M3 Embedder" — dense 1024-dimension plus sparse lexical vectors
- "Hybrid Search" — Qdrant server-side Reciprocal Rank Fusion, IDF modifier on
  the sparse index
- "Section Concordance" — maps repealed IPC, CrPC and Indian Evidence Act
  sections to the 2023 Sanhitas (BNS, BNSS, BSA)
- "Currency Resolver" — marks superseded and repealed sources so they cannot
  ground a user-facing claim
- "Citation Follower" — pulls in provisions a retrieved passage cites
- "Ollama LLM Runtime" — qwen3-14b-16k, temperature 0, seeded, generation
  concurrency 1
Show Reasoning and Verification both calling the Ollama runtime.

LANE 6 — DATA AND INGESTION
Data stores, drawn as cylinders:
- "Qdrant" containing three collections: "global_legal_corpus_v4 (active)",
  "police_case_data", "advocate_case_data"
- "PostgreSQL 16" — 19 tables: users, roles, cases, chat sessions, chat
  messages, documents, jobs, audit logs
- "MinIO" — uploaded case documents and evidence files
Ingestion pipeline, drawn as a chain feeding Qdrant:
  "Source Manifests" → "Fetcher (polite, resumable)" → "Promotion and
  Validation" → "Canonical Manifest (1,036 documents)" → "Extract (PyMuPDF +
  Tesseract OCR)" → "Chunker" → "BGE-M3 Embedder" → "Qdrant"
Add a side box feeding Source Manifests: "Acquisition — India Code DSpace API,
High Courts, NALSA, ministries and regulators".
Attach a note to Promotion: "Quarantines out-of-scope, mistitled and
non-English material with a recorded reason; nothing is deleted."

CROSS-CUTTING (draw as a vertical band on the right touching all lanes)
- "Audit Logging"
- "Per-Role Access Control"
- "Evidence and Currency Metadata"

COLOUR
Clients light grey, API layer blue, routing amber, agent nodes green, data
stores dark teal, ingestion purple. Keep all text black on light fills.

---

## If the AI output is rough

Lucidchart imports Mermaid directly: **File → Import → Mermaid**, or paste
Mermaid into a shape's text in a Lucidchart "Mermaid" block. Ask me and I will
hand you the same architecture as a Mermaid `flowchart LR` you can import
instead — it gives you an exact layout rather than an interpretation.
