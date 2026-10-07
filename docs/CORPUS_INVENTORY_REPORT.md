# Corpus Inventory Report

Audit date: 2026-10-08. Source of truth: `docs/evidence/corpus/inventory.csv`.

## Canonical corpus totals

- 1,036 canonical, SHA-256-unique PDFs
- 42,182 pages
- 1,958,191,901 bytes (1,867.48 MiB; 1.824 GiB)
- 47 detailed categories across 6 top-level segments
- Every recorded local path exists, every recorded byte count matches the file, and canonical IDs are unique

## Top-level segments

| Segment | PDFs | Pages | Bytes | MiB |
|---|---:|---:|---:|---:|
| government_handbooks | 7 | 1,169 | 19,115,229 | 18.23 |
| judgments | 93 | 5,530 | 48,310,186 | 46.07 |
| law_commission_reports | 46 | 4,808 | 136,580,745 | 130.25 |
| official_guidance | 219 | 4,824 | 601,788,219 | 573.91 |
| primary_law | 616 | 24,224 | 1,077,921,632 | 1,027.99 |
| rules_amendments_notifications | 55 | 1,627 | 74,475,890 | 71.03 |
| **Total** | **1,036** | **42,182** | **1,958,191,901** | **1,867.48** |

## Detailed segments

| Segment | PDFs | Pages | Bytes | MiB |
|---|---:|---:|---:|---:|
| government_handbooks | 7 | 1,169 | 19,115,229 | 18.23 |
| judgments/high_court/andhra_pradesh | 14 | 134 | 4,689,410 | 4.47 |
| judgments/supreme_court | 79 | 5,396 | 43,620,776 | 41.60 |
| law_commission_reports | 46 | 4,808 | 136,580,745 | 130.25 |
| official_guidance | 1 | 2 | 294,268 | 0.28 |
| official_guidance/bprd | 5 | 154 | 14,494,133 | 13.82 |
| official_guidance/child_protection | 21 | 854 | 97,231,571 | 92.73 |
| official_guidance/criminal_law_concordance | 3 | 90 | 1,794,320 | 1.71 |
| official_guidance/human_rights | 12 | 240 | 49,499,566 | 47.21 |
| official_guidance/legal_aid | 41 | 1,161 | 154,901,981 | 147.73 |
| official_guidance/mha | 60 | 726 | 124,734,795 | 118.96 |
| official_guidance/ncrb | 8 | 634 | 15,366,729 | 14.65 |
| official_guidance/police_courts | 7 | 275 | 24,522,730 | 23.39 |
| official_guidance/police_investigation | 8 | 157 | 29,215,777 | 27.86 |
| official_guidance/prisons_bail | 50 | 496 | 88,802,072 | 84.69 |
| official_guidance/women_commission | 3 | 35 | 930,277 | 0.89 |
| primary_law/banking_finance | 45 | 2,545 | 29,632,070 | 28.26 |
| primary_law/bns | 2 | 104 | 3,500,891 | 3.34 |
| primary_law/bnss | 4 | 273 | 12,468,464 | 11.89 |
| primary_law/bsa | 1 | 47 | 670,370 | 0.64 |
| primary_law/citizenship_elections | 3 | 101 | 1,687,052 | 1.61 |
| primary_law/civil_procedure | 22 | 566 | 70,954,610 | 67.67 |
| primary_law/constitution | 115 | 1,605 | 40,138,778 | 38.28 |
| primary_law/consumer_protection | 14 | 169 | 10,399,930 | 9.92 |
| primary_law/corporate_commercial | 3 | 423 | 5,891,593 | 5.62 |
| primary_law/disability_welfare | 2 | 57 | 2,658,790 | 2.54 |
| primary_law/education | 8 | 120 | 27,796,746 | 26.51 |
| primary_law/environment | 27 | 481 | 33,124,814 | 31.59 |
| primary_law/family_personal_law | 23 | 497 | 20,117,719 | 19.19 |
| primary_law/health_medical | 33 | 2,331 | 248,758,660 | 237.23 |
| primary_law/health_reproductive | 8 | 225 | 6,810,665 | 6.50 |
| primary_law/infrastructure_utilities | 2 | 123 | 1,645,089 | 1.57 |
| primary_law/insolvency | 6 | 318 | 5,256,069 | 5.01 |
| primary_law/insurance | 41 | 2,645 | 119,859,208 | 114.31 |
| primary_law/labour_welfare | 8 | 962 | 11,711,049 | 11.17 |
| primary_law/legacy_ipc_crpc_evidence | 4 | 216 | 3,648,408 | 3.48 |
| primary_law/other_relevant_laws | 52 | 2,683 | 152,539,904 | 145.47 |
| primary_law/property_land | 12 | 627 | 6,764,092 | 6.45 |
| primary_law/public_administration | 2 | 26 | 650,397 | 0.62 |
| primary_law/securities_markets | 41 | 4,506 | 64,645,029 | 61.65 |
| primary_law/social_justice | 12 | 505 | 11,065,229 | 10.55 |
| primary_law/special_criminal_laws | 26 | 322 | 20,640,672 | 19.68 |
| primary_law/taxation | 41 | 241 | 29,931,645 | 28.55 |
| primary_law/technology_privacy | 30 | 495 | 25,245,574 | 24.08 |
| primary_law/transparency_rti | 4 | 547 | 78,647,590 | 75.00 |
| primary_law/women_children | 25 | 464 | 31,060,525 | 29.62 |
| rules_amendments_notifications | 55 | 1,627 | 74,475,890 | 71.03 |

## Collection gap

The documented acceptance target is approximately 2,500 documents.

- Current accepted corpus: 1,036
- Exact gap to 2,500: **1,464 accepted documents**
- Staged unique candidates not already canonical: 625
- If all 625 pass review, remaining external collection gap: **839**
- Absolute on-disk best case: 725 unique non-canonical PDFs qualify, leaving **739**. This is not a planning assumption because it includes legacy, rejected, and quarantined material.

The repository does not define per-category numeric quotas. Collection should therefore prioritize missing parent Acts and documented coverage gaps rather than inflate already-large segments.

## Physical files versus accepted corpus

The complete `data/` tree contains 3,124 PDF files using 4,963,969,475 bytes (4,734.01 MiB; 4.623 GiB), but only 1,761 unique SHA-256 payloads. The larger physical count includes candidates, legacy copies, duplicates, rejected files, and quarantine material; it must not be reported as the accepted corpus.

| Physical area | Files | Unique payloads | Bytes |
|---|---:|---:|---:|
| Canonical inventory | 1,036 | 1,036 | 1,958,191,901 |
| `data/legal_kb/raw` | 1,662 | 1,094 | 3,093,834,860 |
| Candidate imports | 1,328 | 1,308 | 1,751,919,774 |
| Legacy collections | 134 | 134 | 118,214,841 |
