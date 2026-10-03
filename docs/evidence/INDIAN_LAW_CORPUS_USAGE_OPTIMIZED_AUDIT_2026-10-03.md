# Indian-law corpus: usage-optimised continuation audit

Date: 3 October 2026

## Outcome

The existing corpus was audited before further acquisition. The highest-value next
step is local reconciliation and promotion review, not another broad download pass.
The project already contains a 419-record frozen physical manifest, a 438-row
canonical registry, a completed 400-document v4 vector build, and 80 validated
candidate artifacts across four recent acquisition batches.

No candidate was promoted by this audit. Promotion remains gated on legal-currency,
licensing/access, classification, duplicate, and retrieval-quality review.

## Exact state found

| surface | state |
|---|---:|
| frozen physical manifest | 419 records |
| canonical registry | 438 rows |
| unique canonical SHA-256 values | 400 |
| staged additions represented in canonical registry | 19 |
| v3 ingestion checkpoint | 381 completed, 0 failed, 24,810 chunks |
| v4 ingestion checkpoint | 400 completed, 0 failed, 26,210 chunks |
| configured application collection | `global_legal_corpus_v3` |
| candidate registry entries | 111 |
| validated candidate artifacts | 80 |
| failed candidate acquisitions | 31 |
| active-corpus duplicate SHA-256 groups | 38 |

The application configuration remains on v3 even though v4 is fully built. This
audit does not switch the configured collection because registry truth, metadata,
and regression checks should be reconciled first.

## Material inconsistencies

1. `canonical_documents.jsonl` has 438 rows while the physical JSONL/CSV inventory
   and physical-to-canonical mapping remain at 419.
2. README, VERSION, and provenance material still describe the frozen 419-document
   corpus and do not consistently describe the 19 additions already represented in
   the canonical registry and v4 build.
3. All 19 newer canonical records lack `effective_from`; all lack a populated year,
   and five lack a source URL.
4. Across the broader canonical registry, 438/438 records lack `effective_from`,
   424 remain `current/verify`, and 44 lack year metadata.
5. Candidate registries contain 11 normalized-title duplicates and four exact ID
   collisions. Instrument identity must be resolved by title, jurisdiction,
   consolidation date, and legal status rather than URL or checksum alone.
6. The current metadata does not provide a usable secondary-source licensing gate:
   active and candidate records lack licence, rights, and access-permission fields.
7. Several items are misclassified, including rules/guidance stored as primary law,
   and the canonical child-marriage title incorrectly identifies the 2006 Act as a
   2005 Act.
8. Two AP High Court duplicate-hash groups associate the same bytes with different
   case titles and require source-to-case verification.

## Coverage findings

### Constitution and rights

The corpus contains the Constitution (English, consolidated as on 1 May 2024),
privacy and recent rights cases, criminal-process protections, SC/ST protections,
POSH, POCSO/Juvenile Justice, prison material, and legal-aid material. It is thin on
foundational doctrine. Major absent titles include *Kesavananda Bharati*, *Maneka
Gandhi*, *Minerva Mills*, *S.R. Bommai*, *Navtej Singh Johar*, *Shreya Singhal*,
*Vishaka*, and *D.K. Basu*. Standalone primary-law gaps include civil rights, human
rights, transgender rights, disability rights, manual scavenging, RTE, and canonical
RTI coverage.

### Civil and citizen law

The completed v4 build adds CPC, Limitation, Contract, Specific Relief, Transfer of
Property, RERA/AP RERA, Negotiable Instruments, consumer/e-commerce instruments,
Motor Vehicles, Noise Rules, and POSH material. Remaining high-value gaps include
court fees, AP civil rules/forms/e-filing, ordinary AP tenancy, Easements, consumer
procedure, general tort authorities, and operational citizen guides.

### Family, labour, state law, and secondary sources

The family candidate batch has 34 validated files, including 13 central-law copies,
but also 21 Kerala-specific rules that should not be promoted into an AP/Telangana
collection without an explicit comparative-law purpose. The labour candidate set has
three 2026 Central Rules and implementation guidance, but the four enacted labour-code
URLs failed. AP has useful candidate material; Telangana primary/state coverage is
effectively absent. No meaningful open textbook/university-module collection exists,
and no secondary item should be acquired or promoted until licence/access metadata is
part of the registry schema.

## Local validation batch (zero acquisition traffic)

Fifteen already-downloaded, official-source PDFs were checked with `pdfinfo`, full
text extraction, SHA-256 comparison against the canonical registry, and file-size
verification. All 15 opened successfully, had substantial extractable text, and had
zero exact checksum matches in the canonical registry. `qpdf` is unavailable in the
current environment, so PDF structural validation is based on successful parser open
and full text extraction.

| item | pages | extracted chars/page | canonical SHA match |
|---|---:|---:|---:|
| Family Courts Act, 1984 | 7 | 2,721 | 0 |
| Indian Succession Act, 1925 | 99 | 3,354 | 0 |
| Special Marriage Act, 1954 | 25 | 2,636 | 0 |
| Hindu Marriage Act, 1955 | 13 | 3,355 | 0 |
| Hindu Succession Act, 1956 | 11 | 2,859 | 0 |
| Muslim Personal Law (Shariat) Application Act, 1937 | 3 | 1,852 | 0 |
| Muslim Women (Protection of Rights on Marriage) Act, 2019 | 2 | 2,509 | 0 |
| Indian Christian Marriage Act, 1872 | 26 | 2,683 | 0 |
| Maintenance and Welfare of Parents and Senior Citizens Act, 2007 | 9 | 2,854 | 0 |
| AP Rules under the Registration Act, 1908 | 134 | 1,354 | 0 |
| AP Rights in Land and Pattadar Pass Books Act, 1971 | 11 | 3,020 | 0 |
| AP Agricultural Land Conversion Act, 2006 | 6 | 2,260 | 0 |
| Industrial Relations (Central) Rules, 2026 | 92 | 4,070 | 0 |
| Social Security (Central) Rules, 2026 | 259 | 4,205 | 0 |
| OSH and Working Conditions (Central) Rules, 2026 | 318 | 3,534 | 0 |

These are promotion candidates, not assertions that the texts are current. Each
still needs official consolidation/commencement verification, jurisdiction and type
classification, source-page access terms, and golden-question coverage.

## Targeted retry performed

Only the four unresolved records in the Property/AP batch were retried (two workers,
two attempts, 45-second timeout). Existing valid artifacts were reused and not
re-downloaded. Results were unchanged:

| item | result |
|---|---|
| Indian Easements Act, 1882 | India Code read timeout |
| RFCTLARR Act, 2013 | India Code read timeout |
| Legal Services Authorities Act, 1987 | India Code read timeout; an active-corpus copy already exists |
| Ward Administrative Secretaries Reading Material | official URL returns 404 |

Repeated retries should stop until a current official alternate URL is identified.

## Usage-optimised continuation order

1. Reconcile the 419/438 registry split and document the frozen-v1 versus v4 status.
2. Add licence/access, retrieval, page-count, MIME, size, OCR, currency, and
   verification fields to the candidate-review surface without rewriting immutable
   historical manifests.
3. Resolve semantic duplicates and the four candidate ID collisions.
4. Review and promote a small, question-driven batch from the 15 validated local
   artifacts; build embeddings once for the whole accepted batch.
5. Run the v4 golden set and domain-specific family/civil/AP questions before changing
   the configured collection from v3.
6. Acquire only gaps not already represented locally: AP tenancy, Easements, missing
   rights Acts, a small constitutional landmark set, and current consumer procedure.
7. Establish a licensing register before collecting textbooks or university modules.
8. Build Telangana coverage as a distinct official-source batch rather than mixing
   central-law copies hosted by Telangana institutions with Telangana state law.

This order maximizes corpus value per network request and avoids paying ingestion cost
for documents that may later be rejected as duplicate, out-of-scope, or insufficiently
verified.
