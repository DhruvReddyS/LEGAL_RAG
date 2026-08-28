# Multi-Agent Legal RAG Decision Support

Production-oriented legal decision-support platform built with FastAPI, PostgreSQL,
Qdrant, S3-compatible storage, BGE-M3 embeddings, LangGraph, Next.js, and Tauri.

## Repository layout

```text
backend/                 FastAPI application, migrations, ingestion, retrieval, tests
frontend/                Next.js 14 static-export UI and Tauri v2 desktop scaffold
docker/                  Compose stack and backend image
scripts/                 Operational and corpus-management utilities
docs/                    Specification, implementation plan, handoff, assessments
data/legal_kb/           Versioned active Gold corpus and generated artifacts
data/source_materials/   Inactive legacy sources and candidate imports
```

The only corpus used by the current ingestion and retrieval pipeline is
`data/legal_kb`. Files under `data/source_materials` are archival or candidate
inputs and must not be indexed until they pass provenance, checksum, metadata,
deduplication, and quality validation.

## Start here

- Current state and exact operating commands: [`docs/PROJECT_HANDOFF.md`](docs/PROJECT_HANDOFF.md)
- Ingestion metrics and methodology: [`docs/INGESTION_ASSESSMENT.md`](docs/INGESTION_ASSESSMENT.md)
- Tier 2 scenario and security acceptance: [`docs/TIER2_ACCEPTANCE.md`](docs/TIER2_ACCEPTANCE.md)
- Tiered implementation plan: [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)
- Performance, five-second fast path, scale, and corpus growth: [`docs/PERFORMANCE_AND_CORPUS_SCALING_PLAN.md`](docs/PERFORMANCE_AND_CORPUS_SCALING_PLAN.md)
- Live Fast-mode measurements and acceptance: [`docs/FAST_MODE_ACCEPTANCE.md`](docs/FAST_MODE_ACCEPTANCE.md)
- Adaptive Auto routing and diverse-authority acceptance: [`docs/ADAPTIVE_RAG_ACCEPTANCE.md`](docs/ADAPTIVE_RAG_ACCEPTANCE.md)
- Premium citizen/police/advocate command centres, agents, shortcuts and security acceptance: [`docs/ROLE_BASED_ACCEPTANCE.md`](docs/ROLE_BASED_ACCEPTANCE.md)
- Administrator account governance, corpus expansion and audit acceptance: [`docs/ADMIN_CONTROL_PLANE_ACCEPTANCE.md`](docs/ADMIN_CONTROL_PLANE_ACCEPTANCE.md)
- Latest adversarial RAG stress-test and release decision: [`docs/RAG_STRESS_TEST_REPORT.md`](docs/RAG_STRESS_TEST_REPORT.md)
- Native Tauri package, one-command launch and desktop RBAC acceptance: [`docs/TAURI_DESKTOP_ACCEPTANCE.md`](docs/TAURI_DESKTOP_ACCEPTANCE.md)
- Local demo credentials and role-by-role walkthrough: [`docs/LOCAL_DEMO_USER_MANUAL.md`](docs/LOCAL_DEMO_USER_MANUAL.md)
- Secure other-device topology and production scaling gates: [`docs/MULTI_DEVICE_DEPLOYMENT.md`](docs/MULTI_DEVICE_DEPLOYMENT.md)
- Grounded Document Analyzer and Evidence Inspector acceptance: [`docs/DOCUMENT_ANALYZER_ACCEPTANCE.md`](docs/DOCUMENT_ANALYZER_ACCEPTANCE.md)
- Canonical feature specification: [`docs/FINAL_MULTI_AGENT_LEGAL_RAG_FEATURE_SPEC.docx`](docs/FINAL_MULTI_AGENT_LEGAL_RAG_FEATURE_SPEC.docx)

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
