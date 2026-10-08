# Collection batch ledger — 2026-10-08

Owner: Codex acquisition lane. Promotion and ingestion owner: Claude.

## Outcome

- 14 official-source PDFs downloaded into the ignored
  `data/source_materials/candidate_imports/` review workspace.
- 2,520 pages and 383,699,804 bytes in total.
- 10 PDFs (245 pages; 12,637,799 bytes) are in the priority parent-law batch.
- 4 PDFs (2,275 pages; 371,062,005 bytes) are in the tax/banking batch.
- Every held file starts with a valid PDF signature, opens with Poppler,
  reports a non-zero page count, provides extractable English text, and passed
  first-page visual inspection.
- No promotion, ingestion, embedding, Qdrant write, or canonical count change
  was performed.
- The accepted corpus therefore remains 1,036 documents, with a gross gap of
  1,464 to the 2,500 planning target. If all 14 files in this batch prove
  net-new and are accepted, that gross gap falls to 1,450; combined with the
  625 pre-existing staged candidates, the optimistic external collection gap
  would fall from 839 to 825. These are planning bounds, not acceptance counts.

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
| Income-tax Act, 2025, amended by Finance Act, 2026 | 674 | 118,184,791 | `ee2a32197b8935636c97efbbbf6fc198b3d30a5694bc9ce2c28c6764fa65ab7f` | Held for Claude review; operative from 2026-04-01 |
| Income-tax Rules, 2026 | 423 | 72,323,106 | `0fdd7ece7a8660512fe6c119d96cca594eefe33fa1413ddce3f1c0d0218c1521` | Held for Claude review; rule 1 states commencement on 2026-04-01 |
| Income-tax Act, 1961 legacy consolidation | 1,117 | 179,141,656 | `73d264fd05bc3b19ee003f399aeb50faf7ea36a42f345fa94ebb9b3a2ad0cb93` | Held for transition/repeal-and-savings review; CBDT export starts with six section-139 pages before the full Act begins at PDF page 7 |

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
6. The official CBDT Income-tax Act, 2025 and Income-tax Rules, 2026 PDFs both
   state commencement on 2026-04-01. The 1961 consolidation is legacy material
   and has an exporter page-order anomaly that must not be mistaken for a
   complete-current-law signal.

## Next acceptance action

Claude should compare these payloads against canonical and staged hashes,
verify legal status and current effect, and disposition each as accept,
duplicate, defer, or reject. Only after that may Claude promote and ingest.
