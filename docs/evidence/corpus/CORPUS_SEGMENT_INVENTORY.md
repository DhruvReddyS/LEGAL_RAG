# Corpus segment inventory

Generated: 2026-10-09

The canonical manifest is the production-count authority. Runtime ingestion indexes one file per canonical content hash, so the segment tables are deduplicated exactly as the ingestion pipeline is. Raw and candidate workspaces contain duplicates, rejected files, quarantined material, and review candidates; their physical counts must not be added to the runtime total.

## Exact canonical total

| PDFs | Pages | Bytes | GiB |
|---:|---:|---:|---:|
| 1,563 | 55,321 | 2,528,902,167 | 2.355 GiB |

The manifest contains 1,566 physical file records. 3 are byte-identical alternate copies, leaving 1,563 unique PDFs for indexing.

## Canonical PDFs by top-level segment

| Segment | PDFs | Pages | Bytes | GiB |
|---|---:|---:|---:|---:|
| `government_handbooks` | 7 | 1,169 | 19,115,229 | 0.018 GiB |
| `judgments` | 93 | 5,530 | 48,310,186 | 0.045 GiB |
| `law_commission_reports` | 46 | 4,808 | 136,580,745 | 0.127 GiB |
| `official_guidance` | 221 | 4,861 | 601,906,432 | 0.561 GiB |
| `primary_law` | 1,141 | 37,326 | 1,648,513,685 | 1.535 GiB |
| `rules_amendments_notifications` | 55 | 1,627 | 74,475,890 | 0.069 GiB |

## Canonical PDFs by category

| Category | PDFs | Pages | Bytes | GiB |
|---|---:|---:|---:|---:|
| `government_handbooks` | 7 | 1,169 | 19,115,229 | 0.018 GiB |
| `judgments/high_court/andhra_pradesh` | 14 | 134 | 4,689,410 | 0.004 GiB |
| `judgments/supreme_court` | 79 | 5,396 | 43,620,776 | 0.041 GiB |
| `law_commission_reports` | 46 | 4,808 | 136,580,745 | 0.127 GiB |
| `official_guidance` | 1 | 2 | 294,268 | 0.000 GiB |
| `official_guidance/bprd` | 5 | 154 | 14,494,133 | 0.013 GiB |
| `official_guidance/child_protection` | 21 | 854 | 97,231,571 | 0.091 GiB |
| `official_guidance/criminal_law_concordance` | 3 | 90 | 1,794,320 | 0.002 GiB |
| `official_guidance/human_rights` | 12 | 240 | 49,499,566 | 0.046 GiB |
| `official_guidance/legal_aid` | 41 | 1,161 | 154,901,981 | 0.144 GiB |
| `official_guidance/mha` | 60 | 726 | 124,734,795 | 0.116 GiB |
| `official_guidance/ncrb` | 8 | 634 | 15,366,729 | 0.014 GiB |
| `official_guidance/police_courts` | 9 | 312 | 24,640,943 | 0.023 GiB |
| `official_guidance/police_investigation` | 8 | 157 | 29,215,777 | 0.027 GiB |
| `official_guidance/prisons_bail` | 50 | 496 | 88,802,072 | 0.083 GiB |
| `official_guidance/women_commission` | 3 | 35 | 930,277 | 0.001 GiB |
| `primary_law/banking_finance` | 50 | 2,674 | 31,908,774 | 0.030 GiB |
| `primary_law/bns` | 2 | 104 | 3,500,891 | 0.003 GiB |
| `primary_law/bnss` | 4 | 273 | 12,468,464 | 0.012 GiB |
| `primary_law/bsa` | 1 | 47 | 670,370 | 0.001 GiB |
| `primary_law/citizenship_elections` | 4 | 117 | 2,092,608 | 0.002 GiB |
| `primary_law/civil_procedure` | 34 | 780 | 73,363,333 | 0.068 GiB |
| `primary_law/constitution` | 115 | 1,605 | 40,138,778 | 0.037 GiB |
| `primary_law/consumer_protection` | 15 | 187 | 10,797,809 | 0.010 GiB |
| `primary_law/corporate_commercial` | 7 | 514 | 7,194,499 | 0.007 GiB |
| `primary_law/defence_services` | 3 | 112 | 1,579,785 | 0.001 GiB |
| `primary_law/disability_welfare` | 2 | 57 | 2,658,790 | 0.002 GiB |
| `primary_law/education` | 9 | 131 | 28,048,216 | 0.026 GiB |
| `primary_law/environment` | 35 | 651 | 40,122,118 | 0.037 GiB |
| `primary_law/family_personal_law` | 31 | 699 | 23,647,543 | 0.022 GiB |
| `primary_law/health_medical` | 36 | 2,419 | 252,191,627 | 0.235 GiB |
| `primary_law/health_reproductive` | 8 | 225 | 6,810,665 | 0.006 GiB |
| `primary_law/infrastructure_utilities` | 5 | 181 | 2,722,768 | 0.003 GiB |
| `primary_law/insolvency` | 6 | 318 | 5,256,069 | 0.005 GiB |
| `primary_law/insurance` | 42 | 2,697 | 120,452,129 | 0.112 GiB |
| `primary_law/intellectual_property` | 4 | 170 | 2,385,632 | 0.002 GiB |
| `primary_law/labour_welfare` | 10 | 1,091 | 13,082,539 | 0.012 GiB |
| `primary_law/legacy_ipc_crpc_evidence` | 4 | 216 | 3,648,408 | 0.003 GiB |
| `primary_law/other_relevant_laws` | 453 | 10,010 | 297,439,806 | 0.277 GiB |
| `primary_law/property_land` | 46 | 1,748 | 21,139,694 | 0.020 GiB |
| `primary_law/public_administration` | 4 | 50 | 1,220,896 | 0.001 GiB |
| `primary_law/securities_markets` | 42 | 4,543 | 65,361,962 | 0.061 GiB |
| `primary_law/social_justice` | 17 | 552 | 11,476,827 | 0.011 GiB |
| `primary_law/special_criminal_laws` | 27 | 325 | 21,032,617 | 0.020 GiB |
| `primary_law/taxation` | 45 | 2,565 | 400,774,911 | 0.373 GiB |
| `primary_law/technology_privacy` | 30 | 495 | 25,245,574 | 0.024 GiB |
| `primary_law/transparency_rti` | 4 | 547 | 78,647,590 | 0.073 GiB |
| `primary_law/transport` | 6 | 413 | 5,259,671 | 0.005 GiB |
| `primary_law/women_children` | 40 | 810 | 36,172,322 | 0.034 GiB |
| `rules_amendments_notifications` | 55 | 1,627 | 74,475,890 | 0.069 GiB |

## Review and collection state

- Last promotion batch: 530 PDFs, 13,200 pages, 571,303,619 bytes (0.532 GiB); 530 are now canonical and 0 await promotion.
- Workflow coverage: 22 defined workflows; 22 canonical-complete and 0 awaiting promotion. Runtime readiness still requires index and quality gates.
- Remaining metadata-level source gaps: 0. Further collection is driven by failed evaluations or unresolved currency/commencement evidence, not a target PDF count.
- Two review blockers remain explicit: the CMVR base PDF is an old consolidation requiring amendment reconciliation; the AP tenancy Act requires authoritative commencement/rules evidence.

## Physical workspaces (not additive)

| Workspace | PDF files | Bytes | GiB |
|---|---:|---:|---:|
| `data/legal_kb/raw` | 2,192 | 3,665,138,479 | 3.413 GiB |
| `data/source_materials/candidate_imports` | 1,344 | 2,137,663,064 | 1.991 GiB |

The raw workspace count is larger than the canonical manifest because it also preserves non-canonical files. The candidate workspace is a review backlog, not production data.
