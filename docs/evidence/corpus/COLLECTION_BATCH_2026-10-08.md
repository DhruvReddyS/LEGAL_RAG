# Collection batch ledger — 2026-10-08

Owner: Codex acquisition lane. Promotion and ingestion owner: Claude.

## Outcome

- 11 official-source PDFs downloaded into the ignored
  `data/source_materials/candidate_imports/` review workspace.
- 306 pages and 14,050,251 bytes in total.
- 10 PDFs (245 pages; 12,637,799 bytes) are in the priority parent-law batch.
- 1 DICGC Act/Regulations PDF (61 pages; 1,412,452 bytes) is in the tax/banking
  batch.
- Every held file starts with a valid PDF signature, opens with Poppler,
  reports a non-zero page count, provides extractable English text, and passed
  first-page visual inspection.
- No promotion, ingestion, embedding, Qdrant write, or canonical count change
  was performed.

## Priority parent-law batch

Manifest: `data/source_materials/priority_parent_law_sources_2026-10-08.json`

| Document | Pages | Bytes | SHA-256 |
|---|---:|---:|---|
| Micro, Small and Medium Enterprises Development Act, 2006 | 11 | 5,077,936 | `a137695e263970da9e6efd40e9fd6d6beef658090f1a066c5e679e56bc71425a` |
| Micro, Small and Medium Enterprises Development (Amendment) Act, 2026 | 8 | 472,265 | `b3f0dd79c46e32af3c0e5b497c90d0bfe5d943352b15c664f1b3a40707fde1e2` |
| Biological Diversity Act, 2002 | 20 | 289,803 | `bbf9cf8f12a893c760208482df886056e0e074e766e06aa4ef15424ea396d10b` |
| Biological Diversity (Amendment) Act, 2023 | 15 | 217,544 | `03af902a2b3ea88b100b60cf59e7ae067fa25f9d445368b9078dce1ad8a53892` |
| Commencement notification for the Biological Diversity (Amendment) Act, 2023 | 1 | 349,861 | `6d81533eddca131c99042e6db6257f4900297b09b0d9d85bcbfbe96995cc0314` |
| Corrigendum to the Biological Diversity (Amendment) Act, 2023 | 2 | 60,000 | `26294c48caed6f67b275300f21bbd53bfecc33aca7b3e5bac329a4e66db19887` |
| Biological Diversity Rules, 2024 | 86 | 2,414,630 | `33ec189d783e1124cb9c7f027ea9fabcae850bbb3df1a6753cdebc7fe776f4d1` |
| Biological Diversity (Amendment) Rules, 2025 | 5 | 1,913,922 | `a32a3bcac48955f0285e7a5c589880e6bfa00ac9f5d53c3d969616761d4dc63a` |
| Biological Diversity access-and-benefit-sharing Regulations, 2025 | 28 | 1,512,354 | `15beed19974f0948db417a6a0be39d147f8ff5b1871824888a2062b37a4f20e0` |
| Food Safety and Standards Act, 2006 | 69 | 329,484 | `4af5224f4a0e8e506919ea1659d5066e6fc0bc3372859ca4eda60442f3be0e6a` |

## Tax and banking batch

Manifest: `data/source_materials/tax_parent_sources_2026-10-08.json`

| Document | Pages | Bytes | SHA-256 | Disposition |
|---|---:|---:|---|---|
| DICGC Act, 1961 and General Regulations, 1961 | 61 | 1,412,452 | `d925b1a912f90c415c6a83df6c363c14493f35dbfc1be4b18677ce76cce10d4d` | Held for Claude review |
| Income-tax Act, 2025, amended by Finance Act, 2026 | - | - | - | Official CBDT endpoint returned HTTP 403; queued for browser-assisted retrieval |
| Income-tax Rules, 2026 | - | - | - | Official CBDT endpoint returned HTTP 403; queued for browser-assisted retrieval |
| Income-tax Act, 1961 legacy consolidation | - | - | - | Official CBDT endpoint returned HTTP 403; queued for browser-assisted retrieval |

## Currency findings Claude must preserve

1. The MSMED Amendment Act, 2026 received assent and was gazetted on
   2026-08-13, but its commencement clause requires a Central Government
   notification. No official commencement notification was located in this
   batch review. Do not mark the amendments in force without finding it.
2. The Biological Diversity (Amendment) Act, 2023 is in force from 2024-04-01
   under the official commencement notification. Apply its official
   corrigendum.
3. The Biological Diversity Rules, 2024 superseded the 2004 Rules and are in
   force from 2024-12-21. They must be read with the Biological Diversity
   (Amendment) Rules, 2025, in force from 2025-11-01.
4. The 2025 access-and-benefit-sharing Regulations supersede the 2014
   guidelines subject to their savings clause.
5. The Food Safety Act source is an official FSSAI copy, but later amendments
   still require a separate current-effect review.

## Next acceptance action

Claude should compare these payloads against canonical and staged hashes,
verify legal status and current effect, and disposition each as accept,
duplicate, defer, or reject. Only after that may Claude promote and ingest.
