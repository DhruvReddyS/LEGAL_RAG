# Corpus collection plan — 2026-10-08

## Decision summary

Finish a quality-weighted Corpus V1 before adding more retrieval complexity.
The priority is authoritative parent law and source coverage, not raw PDF
count. Collection, promotion, ingestion, and evaluation remain separate gates.

## Current numbers

| Measure | Count |
|---|---:|
| Canonical documents | 1,036 |
| Corpus V1 planning target | 2,500 |
| Gross gap to target | 1,464 |
| Unique staged, non-canonical candidates | 625 |
| Optimistic remaining external collection gap if every staged file passes | 839 |

The 839 figure is a lower bound, not a promise: duplicates, poor scans,
non-citable titles, out-of-scope material, and superseded instruments must be
rejected. A smaller authoritative corpus is preferable to 2,500 weak files.

## Refreshed gap review

The 2026-10-03 assignment is stale because several named parent Acts are now
canonical. Confirmed canonical holdings include the Reserve Bank of India Act,
Banking Regulation Act, SEBI Act, Insurance Act, Customs Act, FEMA, Payment and
Settlement Systems Act, Chit Funds Act, Air Act, Water Act, forest-conservation
law, wildlife-protection law, Clinical Establishments Act, transplantation
law, National Medical Commission Act, Epidemic Diseases Act, Right to
Education law, Electricity Act, and Telecommunications Act, 2023.

Already staged for Claude's acceptance review, but not canonical at this
snapshot: Securities Contracts (Regulation) Act, CGST Act, DICGC Act, National
Green Tribunal Act, Food Safety and Standards Act, Drugs and Cosmetics Act,
and Mental Healthcare Act.

High-value gaps still requiring an official source or final acceptance include
the current income-tax regime, MSMED Act, 2006, and Biological Diversity Act,
2002. The income-tax request must no longer be treated as only a request for
the 1961 Act: the Income-tax Act, 2025 took effect on 1 April 2026. The current
Act and Rules belong in the current-law lane; the 1961 text belongs in a
clearly labelled legacy/transition lane.

## First Codex batch

Manifest: `data/source_materials/tax_parent_sources_2026-10-08.json`

1. Income-tax Act, 2025, official CBDT consolidation as amended by the Finance
   Act, 2026.
2. Income-tax Rules, 2026, official CBDT English notification.
3. Income-tax Act, 1961, official legacy consolidation for transition and
   pre-2026 matters, explicitly flagged as repealed-with-savings review.
4. DICGC Act, 1961 and General Regulations, 1961, official DICGC-hosted
   combined publication (Act through August 2023; Regulations through February
   2025).

These files enter `candidate_imports/` only. Claude validates legal status,
currency, duplicates, title quality, text extraction, and promotion.

Fetch result: the DICGC combined publication downloaded and passed basic PDF
validation (61 pages, 1,412,452 bytes, extractable English text, SHA-256
`d925b1a912f90c415c6a83df6c363c14493f35dbfc1be4b18677ce76cce10d4d`).
The three initial CBDT endpoints returned HTTP 403 to the automated fetcher.
Browser-assisted review exposed the official CBDT media endpoints, and all
three files were then downloaded and validated: 2,214 pages and 369,649,553
bytes combined. The legacy 1961 export starts with six section-139 pages before
the full Act begins at PDF page 7, so Claude must review its internal ordering
before promotion. No unofficial substitute was used.

## Work sequence

### Gate 1 — Triage the existing 625

Claude generates an acceptance ledger by document: accept, reject, defer, or
duplicate, with a reason. Promote in domain-sized batches and preserve the
source URL and currency note. This is the fastest path to usable coverage and
prevents collecting duplicates.

### Gate 2 — Fill parent-law gaps

Codex collects official ministry, regulator, court, and statutory-body sources
in batches of 25–50. Each batch starts with a canonical-versus-candidate check.
Order:

1. Current tax and banking parent material.
2. MSMED and biodiversity parent law.
3. Remaining central and Andhra Pradesh/Telangana parent-law gaps identified
   by the coverage matrix.
4. Only then, high-value rules, regulations, binding directions, and leading
   judgments.

### Gate 3 — Build a coverage matrix

Track each legal topic across: parent Act, current rules/regulations, material
amendments or consolidations, authoritative guidance, and leading judgments.
Record jurisdiction, effective dates, repeal/savings status, source authority,
language, OCR quality, and last currency review. A topic is complete only when
the documents necessary to answer and cite ordinary user questions are held.

### Gate 4 — Acceptance controls

Before promotion, require:

- official or otherwise explicitly approved authoritative host;
- English citable title and unique filename;
- valid, readable PDF and usable text extraction/OCR;
- correct jurisdiction and document type;
- legal-status and currency review, including repeal and transition warnings;
- duplicate and near-duplicate check;
- relevance to citizens, police, advocates, or courts;
- provenance retained for every file.

### Gate 5 — Freeze and evaluate Corpus V1

After high-priority coverage is complete, freeze a versioned manifest, let
Claude perform one controlled promotion/ingestion run, then run retrieval and
answer evaluations on an idle machine. Release only if citation correctness,
unsupported-claim, abstention, retrieval, freshness, privacy, and latency gates
pass.

## Batch ledger

For every batch record: owner, date, manifest, attempted URLs, downloaded,
failed, duplicates, promoted, rejected with reasons, canonical total, staged
total, remaining high-priority gaps, and the commit. Counts are snapshots and
must be regenerated after promotion; never add independently measured counts
together without deduplication.

## Definition of collection-complete

Collection is complete when the coverage matrix has no unresolved P0 parent
law gaps, every accepted file has provenance and currency metadata, staged
candidates have dispositions, and Corpus V1 passes the release gates. Reaching
2,500 files alone does not satisfy this definition.
