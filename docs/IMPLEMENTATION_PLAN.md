# Multi-Agent Legal RAG Platform — Implementation Plan

This plan follows `FINAL_MULTI_AGENT_LEGAL_RAG_FEATURE_SPEC.docx`, which is the
scope-frozen source of truth. A phase is complete only when its exit criterion
is demonstrably satisfied.

The ordered performance, under-five-second Fast mode, deployment scaling, and
global corpus expansion work is specified in
[`PERFORMANCE_AND_CORPUS_SCALING_PLAN.md`](PERFORMANCE_AND_CORPUS_SCALING_PLAN.md).

## Current status

- [x] Tier 0.1: exact monorepo scaffold and FastAPI `/health` endpoint
- [x] Tier 0.2: Compose definition, health checks, named volumes, backend image,
  and optional Ollama profile
- [x] Tier 0.2 runtime verification: PostgreSQL, Qdrant, backend, and host Ollama
- [x] Tier 0.3: SQLAlchemy 2.0 async models and reversible Alembic migration
- [x] Tier 0.4: three isolated Qdrant collections with dense/sparse vectors and payload indexes
- [x] Tier 0.5: JWT access/refresh auth, bcrypt hashing, seeded RBAC, and case ownership checks
- [x] Remaining P0 infrastructure: MinIO boundary, audit logs, migrations,
  health checks, and integration acceptance
- [x] P1 ingestion/OCR: 381 canonical documents, 17,426 pages, 25,517 chunks,
  25,517 BGE-M3 dense+sparse embeddings, and strict validation
- [x] P1 retrieval: Qdrant RRF hybrid retrieval, BGE reranking, and 12/12 smoke queries
- [x] P1 agents/chat: bounded LangGraph verification loop, citations, confidence,
  PostgreSQL sessions, ownership, memory, and audit traces
- [x] P1 citizen frontend: Next.js 14 static export, Tailwind/shadcn, citation UI,
  and HttpOnly-cookie web authentication
- [x] P1 native packaging acceptance: Tauri v2 Apple Silicon `.app` and `.dmg`,
  branded bundle, local signature, API/CSP hardening, four-role login checks and
  one-command service launcher
- [x] P2 case workspaces and ownership-isolated general/case-specific retrieval
- [x] P2 PDF/text private evidence indexing with OCR fallback and role collections
- [x] P2 immutable, grounded FIR drafting with explicit missing-field handling
- [x] P2 advocate defence analysis with scenario/legal source separation,
  unsafe-tactic rejection, independent verification, and opposing points
- [x] P2 professional workspace frontend for the accepted vertical slice
- [x] Fast Research mode: startup-warmed BGE retrieval, hashed embedding cache,
  no-reranker evidence brief, conservative relevance gate, per-stage timings,
  request IDs, visible Fast/Deep UI, and live p95 448.99 ms at concurrency 1
- [x] Adaptive Corrective Hybrid RAG: deterministic Auto routing, auditable
  complexity signals, focused-query Fast selection, complex/case-scoped Deep
  selection, distinct-authority citation selection, and transparent Auto UI
- [x] Premium role operating system: distinct citizen/police/advocate command
  centres, navigation, specialist-agent suites, command palette/shortcuts,
  professional evidence workflows, role-context LangGraph traces, owned
  case-aware Deep retrieval, and live cross-role isolation acceptance
- [x] Administration control plane: professional-account creation/suspension,
  inactive-session enforcement, governed PDF corpus staging/validation/publication,
  immutable Gold plus searchable verified-extended tiers, audit UI and live acceptance
- [x] Adversarial Fast/Auto stress testing: hallucination traps, source diversity,
  private-data override, safe abstention, visible UX and Fast/Deep workload isolation
- [x] P2 Document Analyzer and Source Provenance/Evidence Inspector: exact
  structured contract, private chunk grounding, corpus cross-check for proposed
  sections, seven-field inspector, role workbench and live Ollama acceptance
- [ ] Deep interactive acceptance: the local 14B multi-agent workflow exceeded
  the 180-second stress-test deadline and needs bounded asynchronous execution
- [ ] P2 judgment tools, export studio, amendment tracker, feedback UI, durable
  background analysis jobs and streaming

## P0 — Infrastructure

Deliver:

1. Monorepo and environment scaffold.
2. Docker Compose stack for PostgreSQL, Qdrant, backend, and optional Ollama.
3. SQLAlchemy 2.0 async models and Alembic migrations for every specified table.
4. Qdrant initialization for all three isolated collections.
5. S3-compatible object storage configuration and storage service boundary.
6. JWT access/refresh authentication, field-level RBAC, ownership checks, and
   audit foundations.
7. Automated infrastructure and authorization tests.

Exit criterion: the complete stack starts reproducibly, migrations and vector
initialization succeed, authentication and ownership isolation are tested, and
the health endpoints are demoable.

## P1 — Verified RAG MVP

Deliver ingestion/OCR, BGE dense and sparse retrieval, hybrid fusion, reranking,
query understanding, retrieval, reasoning, citation verification, LangGraph
orchestration, chat persistence/API, citizen chat UI, and secure auth UI.

Exit criterion: a seeded legal question runs end-to-end and returns an answer
whose important claims resolve to verified corpus passages.

Status: **met**. The accepted FIR query returned two verified page citations at
confidence 0.625 in 47.18 seconds. Native Tauri packaging and local runtime
acceptance are complete; Apple Developer ID signing/notarization is required
only before external distribution.

## P2 — Professional Core

Deliver the case workspace, case-specific/general search, document analyzer,
Legal Document Studio, versioning/export, amendment tracking, confidence badges,
and the source-provenance inspector.

Exit criterion: police and advocate users can work on isolated cases and review
the evidence behind analysis and drafts.

Status: **first vertical slice met**. Case isolation, evidence ingestion,
scoped retrieval, FIR drafting, advocate analysis, audit logs, and frontend flows
are accepted. The remaining P2 features listed above are not yet complete.

## P3 — Case Intelligence

Deliver timeline extraction, evidence mapping, missing-information detection,
statement contradiction analysis, and the provenance-aware case knowledge graph.

Exit criterion: an uploaded demo case produces reusable structured artifacts,
with conflicts and uncertain extractions visible for human review.

## P4 — Police and Advocate Intelligence

Deliver the police investigation checklist, advocate strategy engine,
argument–precedent mapping, and bounded multi-pass deep research.

Exit criterion: every recommendation or strategic proposition links to case
evidence, legal authority, or an explicit insufficient-evidence state.

## P5 — Flagship Virtual Courtroom

Deliver opening argument, independent opposition retrieval/counterargument,
rebuttal, bounded sur-rebuttal, verification, evaluation, Debate Report, and
interactive cross-examination mode.

Exit criterion: the system evaluates grounding and argument quality without
presenting the result as a prediction of a real judgment.

## P6 — Academic Evaluation

Deliver a 50–100-item golden dataset and compare vector-only, hybrid, hybrid plus
reranker, and full verified multi-agent RAG using retrieval, generation,
citation, hallucination, and latency metrics.

Exit criterion: reproducible tables and graphs demonstrate the contribution of
each architectural stage.

## P7 — Stretch

Attempt multilingual support, voice input, offline fallback, enhanced PII
anonymization, and live agent-trace visualization only after P0–P6 pass.
