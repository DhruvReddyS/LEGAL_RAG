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
- Milestone plan from the current system to the target product: [`docs/PRODUCT_ROADMAP.md`](docs/PRODUCT_ROADMAP.md)
- Current corpus-quality plan and release gates: [`docs/evidence/corpus/COVERAGE_DRIVEN_PLAN.md`](docs/evidence/corpus/COVERAGE_DRIVEN_PLAN.md)
- Measurements, with the configuration each was taken under: [`docs/evidence/`](docs/evidence/)

Do not commit `.env`, start overlapping ingestion workers, or use
`docker compose down -v` unless persistent database/vector/object data is
intentionally being deleted.

## Current status

Citizen, police, advocate and admin workflows are implemented. The remaining
work is release quality: finish the v5 index, repair its payload-only metadata,
run the complete gate suite, and cut over only if it beats the live fallback.

| | |
|---|---|
| Live corpus | `global_legal_corpus_v4`, 49,684 points |
| v5 candidate | 1,563 unique PDFs, 55,321 pages, 2.355 GiB; rebuild in progress |
| Minimum-source coverage | 22/22 defined workflows canonical-complete |
| Canonical provenance | 1,563/1,563 official source URLs verified |
| Section coverage | BNSS 100%, BSA 99%, BNS 96% |
| Section concordance | 2,596 pairs from the official NCRB tables |

Four CI gates guard the qualities that matter, and each exists because
something got past the ones before it: correctness, cross-tenant isolation,
retrieval quality, and answer quality. A fifth check asks whether the
provision that *governs* a question is reachable at all -- recall cannot,
because its predicates match any passage containing a phrase, and a judgment
quoting BNSS s.173 satisfies the FIR item while the section itself is absent
from the top hundred.

The measured limitations and release thresholds are in
[`docs/evidence/corpus/COVERAGE_DRIVEN_PLAN.md`](docs/evidence/corpus/COVERAGE_DRIVEN_PLAN.md).
The target is zero unsupported legal claims, claim-level citations, explicit
currency warnings, and precise abstention when governing evidence is absent or
uncertain—not a raw PDF count.
