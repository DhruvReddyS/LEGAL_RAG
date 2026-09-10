# Multi-Agent Legal RAG Decision Support

Production-oriented legal decision-support platform built with FastAPI, PostgreSQL,
Qdrant, S3-compatible storage, BGE-M3 embeddings, LangGraph, Next.js, and Tauri.

## Repository layout

```text
backend/                 FastAPI application, migrations, ingestion, retrieval, tests
frontend/                Next.js 14 static-export UI and Tauri v2 desktop scaffold
docker/                  Compose stack and backend image
scripts/                 Operational and corpus-management utilities
docs/                    Architecture reference, operations, pending work, evidence
data/legal_kb/           Versioned active Gold corpus and generated artifacts
data/source_materials/   Inactive legacy sources and candidate imports
```

The only corpus used by the current ingestion and retrieval pipeline is
`data/legal_kb`. Files under `data/source_materials` are archival or candidate
inputs and must not be indexed until they pass provenance, checksum, metadata,
deduplication, and quality validation.

## Start here

- What the system is and how every part works: [`docs/PRD.md`](docs/PRD.md)
- Running, releasing, sharing and backing it up: [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- What is pending and what each problem needs: [`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md)
- Measurements, with the configuration each was taken under: [`docs/evidence/`](docs/evidence/)

Do not commit `.env`, start overlapping ingestion workers, or use
`docker compose down -v` unless persistent database/vector/object data is
intentionally being deleted.

## Current status

Every planned module is built. Citizen, police, advocate and admin are
feature-complete; the advocate debate room is the one deliberate omission,
and [`docs/PRD.md`](docs/PRD.md) §15 explains what it would cost.

| | |
|---|---|
| Corpus | `global_legal_corpus_v3`, 25,323 points (419 curated + 5 extended sources) |
| Backend tests | 956 |
| Cross-tenant red team | 36, passing |
| Frontend tests | 38 |
| Section coverage | BNSS 100%, BSA 99%, BNS 96% |
| Section concordance | 2,596 pairs from the official NCRB tables |

Four CI gates guard the qualities that matter, and each exists because
something got past the ones before it: correctness, cross-tenant isolation,
retrieval quality, and answer quality. A fifth check asks whether the
provision that *governs* a question is reachable at all -- recall cannot,
because its predicates match any passage containing a phrase, and a judgment
quoting BNSS s.173 satisfies the FIR item while the section itself is absent
from the top hundred.

The measured limitations are in [`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md),
each with the diagnosis rather than the symptom. The shortest summary: the
system knows what it does not know, refuses when the corpus cannot answer,
and never publishes a claim whose evidence was not retrieved -- that last one
measured at zero across every question in the evaluation set.
