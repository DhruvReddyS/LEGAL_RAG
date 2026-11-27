# Multi-Agent Legal RAG Decision Support

Production-oriented legal decision-support platform built with FastAPI, PostgreSQL,
Qdrant, S3-compatible storage, BGE-M3 embeddings, LangGraph, Next.js, and Tauri.

## Repository layout

```text
backend/                 FastAPI application, migrations, ingestion, retrieval, tests
frontend/                Next.js 14 static-export UI and Tauri v2 desktop scaffold
docker/                  Compose stack and backend image
scripts/                 Operational and corpus-management utilities
docs/                    The six project documents, plus evidence and academic material
data/legal_kb/           Versioned active Gold corpus and generated artifacts
data/source_materials/   Inactive legacy sources and candidate imports
```

The only corpus used by the current ingestion and retrieval pipeline is
`data/legal_kb`. Files under `data/source_materials` are archival or candidate
inputs and must not be indexed until they pass provenance, checksum, metadata,
deduplication, and quality validation.

## Start here

Six documents, indexed at [`docs/README.md`](docs/README.md). These are the
documents we follow.

- What Corpusil is, and every feature with its state: [`docs/01-PRODUCT.md`](docs/01-PRODUCT.md)
- How a question becomes an answer, on one page: [`docs/architecture/corpusil-overview.png`](docs/architecture/corpusil-overview.png)
- How it works, component by component: [`docs/02-ARCHITECTURE.md`](docs/02-ARCHITECTURE.md)
- How it is measured, and what is still wrong: [`docs/03-EVIDENCE.md`](docs/03-EVIDENCE.md)
- Running it, building the corpus, cutting a release: [`docs/04-OPERATIONS.md`](docs/04-OPERATIONS.md)
- Where data lives and how it ships: [`docs/05-RELEASE.md`](docs/05-RELEASE.md)
- What we build next, in what order: [`docs/06-PLAN.md`](docs/06-PLAN.md)
- Measurements, with the configuration each was taken under: [`docs/evidence/`](docs/evidence/)

Do not commit `.env`, start overlapping ingestion workers, or use
`docker compose down -v` unless persistent database/vector/object data is
intentionally being deleted.

## Current status

Citizen, police, advocate and admin workflows are implemented, with a desktop app for macOS
and Windows. As of 27 November 2026 (release 0.4.3):

| | |
|---|---|
| Serving corpus | `global_legal_corpus_v6`, 1,593 documents, 86,127 passages |
| Quality gates (`v8-final`) | 6 of 7 passed; latency passes on speed, fails on two citation floors (see [`docs/03-EVIDENCE.md`](docs/03-EVIDENCE.md)) |
| Answers, 102 golden questions | correct refusals 1.000, unsupported claims 0 of 1,191, currency 1.000 |
| Retrieval | citation accuracy@5 0.413, recall@5 0.500 |
| Speed, quiet host | Fast p95 1.58 s, Deep p50 38.6 s |
| Tests | 2,978 backend, 346 frontend unit, 164 browser |
| Not yet done | human review of answers (sheet ready), native review of Hindi and Telugu |

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
