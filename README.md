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

Tier 0 and the verified web RAG MVP are complete: the Gold corpus, BGE-M3/Qdrant
retrieval, LangGraph legal-agent workflow, PostgreSQL chat persistence, secure
cookie authentication, and Next.js static frontend are implemented and tested.
The first Tier 2 professional vertical slice is also accepted: isolated case
workspaces, private evidence indexing, scoped search, immutable FIR drafting,
and verified advocate defence analysis. The frontend is now a role-specific
legal operating console with dedicated citizen, police and advocate command
centres, agent suites, keyboard commands and professional workspaces. The native
Tauri Apple Silicon `.app` and `.dmg` are built and locally accepted; remaining
Tier 2 work is tracked in the implementation plan.
