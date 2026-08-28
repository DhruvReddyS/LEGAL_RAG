# Tier 2 professional-workflow acceptance

Final snapshot: **2026-08-25 IST**.

## Accepted scope

- Police and advocate case creation, listing, reading, updating and archival.
- Reusable RBAC dependency enforces owner and professional-role match before a
  case handler, embedder or Qdrant request runs.
- S3 evidence upload and idempotent PDF/UTF-8 indexing. Scanned PDF pages use
  Tesseract; private chunks go only to `police_case_data` or
  `advocate_case_data` with `case_id` payload filters.
- General search combines Gold plus every authorized case; case-specific search
  combines Gold plus one owner-authorized case. The query is embedded once and
  candidates from all permitted collections are reranked together.
- FIR drafting extracts explicit facts, retrieves Gold authority, preserves
  uncertainty, exposes missing fields and saves immutable versions.
- Advocate defence analysis retrieves conscious-possession/prosecution-burden
  authority, labels the submitted scenario as unverified, requires scenario and
  legal sources, rejects unknown source IDs and unsafe tactics, independently
  verifies claims, and publishes only direct `yes` entailments.
- Next.js professional workspace exposes all accepted operations.

## Automated acceptance

| Gate | Result |
|---|---:|
| Backend tests | 72 passed |
| Cross-owner case read/update | Rejected before handler |
| Cross-owner evidence indexing | Rejected before embedding |
| Scoped Qdrant target inspection | Only owner-authorized case IDs |
| Evidence re-index | Same document and point IDs; no duplicate row |
| Unsafe defence tactic test | Rejected |
| Invented defence source/alibi test | Rejected |
| Partially supported compound chat claim | Suppressed |
| FIR version test | Versions 1 and 2 retained |
| Next.js 14 production/type build | Passed |
| Strict Gold validation | 381 documents, 25,517 points, 0 issues |
| Legal retrieval smoke suite | 12/12 passed |
| Docker services | PostgreSQL, Qdrant, MinIO and backend healthy |

The only recurring warning is Passlib importing Python's deprecated `crypt`
module. Password hashing remains functional; migration away from the deprecated
compatibility path should occur before Python 3.13.

## Live missing-dog scenarios

General chat query asked for missing-dog reporting steps, documents and the FIR
threshold without assuming theft. The first implementation bundled unsupported
practical suggestions under one partially supported citation. The final response
layer now suppresses all partial compound claims.

Final live general-chat result:

- Wall time: **157.08 s**, including one bounded retrieval retry.
- Evidence: **insufficient**, confidence **0.0**, citations **0**.
- Result: explicit insufficient-evidence response. This is the correct behavior
  because the Gold corpus supports the cognizable-offence FIR rule but does not
  support pet-specific documents and operational steps.

Final live dedicated FIR-drafting result, using Qwen 14B, BGE-M3, the reranker,
Qdrant and a rolled-back temporary PostgreSQL transaction:

- Wall time: **22.29 s**.
- Version: **1**; status: **draft**.
- Extracted subject: `brown Labrador Bruno`.
- Extracted identifier: `Collar number PET-204`.
- Required missing fields: **0**.
- Retrieved Gold authorities: **5**.
- The professional-review disclaimer and uncertainty that nobody saw the dog
  being taken were both preserved.
- The temporary user, case and draft were rolled back; no demo rows remain.

This separation is intentional: general legal chat refuses unsupported
pet-specific guidance, while the structured drafting tool can faithfully format
user-supplied facts without asserting that theft occurred or that an FIR must be
registered.

## Live advocate scenario

Scenario: a delivery driver borrowed a vehicle; a sealed prohibited package was
found under a rear seat; knowledge was denied; fingerprints were absent; witness
times conflicted; the owner had earlier access.

Final live result:

- Wall time: **143.50 s**.
- Proposed points: **5**.
- Directly verified and published: **4**.
- Rejected: **1**.
- Confidence: **0.80**, evidence badge **moderate**.
- External Gold citations: **6**, plus the separately labeled unverified user
  scenario.
- Accepted output covered conscious possession, foundational facts before NDPS
  presumptions, an evidentiary gap, and further facts needed.
- No evidence destruction, concealment, fabrication, witness influence or
  outcome prediction was produced.

The self-hosted Qwen profile rejects some nested JSON Schemas as sampler grammar.
The client now detects that exact error and falls back to JSON mode followed by
Pydantic validation. Complex structured calls use a bounded 1,800-token output;
ordinary chat remains bounded at 900 tokens.

## Known current-law limitation

All 25,517 Gold points conservatively carry `is_current=false` because official
consolidation/current-law review has not yet been completed. Tier 2 workflows do
not silently claim currency: they retrieve verified Gold evidence without the
empty current-only filter and display mandatory professional currency warnings.
The Amendment Tracker is therefore the next high-priority accuracy feature.

## Repeatable commands

Run the complete regression suite exactly as documented in
`docs/PROJECT_HANDOFF.md`, then:

```bash
QDRANT_URL=http://localhost:6333 LEGAL_KB_ROOT="$PWD/data/legal_kb" \
  HF_HOME="$PWD/data/legal_kb/cache/models" HF_HUB_OFFLINE=1 \
  TRANSFORMERS_OFFLINE=1 PYTHONPATH="$PWD/backend" EMBEDDING_DEVICE=auto \
  .venv-ingest/bin/python -m app.ingestion.retrieval_smoke
```

The reusable live scenario harness is `scripts/tier2_scenario_acceptance.py`.
