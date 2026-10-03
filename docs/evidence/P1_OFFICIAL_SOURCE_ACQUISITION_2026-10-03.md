# P1 official-source acquisition — 3 October 2026

## Outcome

The requested source map was converted into a machine-readable, official-source-only
registry and staged under `data/source_materials/candidate_imports`. Nothing in this
batch was promoted into the live corpus: every candidate still needs legal-currency,
extraction and retrieval review.

| batch | registry records | valid local artifacts | failed official downloads |
|---|---:|---:|---:|
| existing citizen-law Phase A | 17 | 16 | 1 |
| new P1 expansion | 37 | 11 | 26 |
| combined staged artifacts | 54 | 27 | 27 |

Four P1 instruments whose new downloads timed out are already stored in the canonical
corpus: the Information Technology Act, 2000; Legal Services Authorities Act, 1987;
Protection of Women from Domestic Violence Act, 2005; and Protection of Women from
Domestic Violence Rules, 2006. A Prohibition of Child Marriage Act document is also
present, but its canonical title/year metadata needs review.

## New validated P1 artifacts

| domain | document | pages/type |
|---|---|---:|
| family law | Guardians and Wards Act, 1890 | 17 |
| cyber/data | IT Intermediary Rules, consolidated to 10 February 2026 | 33 |
| cyber/data | Digital Personal Data Protection Rules, 2025 | 41 |
| cyber/data | Data Protection Board establishment notification, 2025 | 2 |
| cyber/data | Data Protection Board membership notification, 2025 | 2 |
| cyber/data | CERT-In section 70B directions portal snapshot | HTML |
| domestic violence | MWCD legislation portal snapshot pointing to the 2006 Rules | HTML |
| labour | Industrial Relations (Central) Rules, 2026 | 92 |
| labour | Social Security (Central) Rules, 2026 | 259 |
| labour | OSH and Working Conditions (Central) Rules, 2026 | 318 |
| labour | Social Security implementation guidance dated 29 January 2026 | 12 |

All PDF files passed magic-byte and minimum-size validation and have SHA-256 hashes in
the acquisition manifest. Page counts were checked with `pdfinfo`. The HTML files are
snapshots of official dynamic portals and must not outrank primary legislation.

## Important currency corrections to the supplied map

- The Digital Personal Data Protection Act is no longer simply “status unknown.” Its
  provisions have staged commencement dates beginning 13 November 2025.
- The final Digital Personal Data Protection Rules, 2025 were notified, also with
  staged commencement.
- The Data Protection Board of India was established in November 2025.
- Final Central Rules for Industrial Relations, Social Security and Occupational
  Safety/Health/Working Conditions were published in May 2026.
- Ministry material records enforcement of the Code on Social Security from
  21 November 2025. The exact Gazette commencement notification should be captured
  before corpus promotion.

## Unresolved official downloads

India Code returned timeouts or 504 responses for 22 P1 Acts during two independent
passes. These include the main family-law set, succession, RTI, registration,
mediation, DPDP Act, RTE and disability law. No partial files were retained.

Four old Ministry of Labour file URLs now return 404 after redirecting to the redesigned
site: the four principal labour-code PDFs. Their current 2026 Central Rules were
successfully captured, but the enacted Code texts still need replacement URLs.

The Andhra Pradesh Tenancy Act remains the single failure in the earlier Phase-A batch;
the India Code upload endpoint timed out.

## Files and rerun

- Registry: `data/source_materials/p1_official_sources_2026-10-02.json`
- Staged P1 files: `data/source_materials/candidate_imports/citizen_law_p1_2026-10-02/`
- P1 manifest: `data/source_materials/candidate_imports/citizen_law_p1_2026-10-02/_logs/acquisition_manifest.json`
- Earlier Phase-A files: `data/source_materials/candidate_imports/citizen_law_phase_a/`

Retry when India Code is healthy:

```bash
python scripts/acquire_citizen_corpus.py \
  --registry data/source_materials/p1_official_sources_2026-10-02.json \
  --output data/source_materials/candidate_imports/citizen_law_p1_2026-10-02 \
  --timeout 90 --retries 4 --workers 2
```

The downloader skips existing valid files, so a retry only fills gaps unless `--force`
is supplied.

## Promotion gate

Before ingestion, confirm consolidation dates, commencement and repeal metadata,
collect Andhra Pradesh amendments/rules where relevant, extract and inspect text, remove
duplicates against `canonical_documents.jsonl`, and add domain-specific golden questions.
