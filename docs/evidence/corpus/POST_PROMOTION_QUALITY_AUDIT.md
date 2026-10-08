# Post-promotion corpus quality audit

Generated: 2026-10-08
Scope: canonical-manifest metadata only; this is not proof of active-index readiness.

## Exact canonical inventory

| Measure | Value |
|---|---:|
| Manifest rows | 1,566 |
| Unique documents by SHA-256 | 1,563 |
| Duplicate-checksum rows | 3 |
| Pages | 55,321 |
| Size | 2.355 GiB |

## Latest promotion batch

The latest unique batch is dated 2026-10-08 and contains 527 documents / 13,139 pages. The manifest gained 530 rows, while checksum deduplication yields 527 unique documents.

| Queue | Count |
|---|---:|
| Latest-batch records in `other_relevant_laws` | 401 |
| Latest-batch records flagged for OCR | 7 |

## Whole-manifest quality queues

| Queue | Count | Interpretation |
|---|---:|---|
| Source URL present | 1,553/1,563 | Citation can expose an origin link when the indexed payload preserves it. |
| Verified official | 1,552/1,563 | Host provenance passed the metadata rule. |
| Currency note present | 1,161/1,563 | A note is not proof of currency; it records the review basis or warning. |
| OCR required | 101 | Must not be treated as searchable until OCR/extraction is verified. |
| Broad fallback category | 453 | Reclassification queue; broad routing can dilute retrieval. |

## Explicit high-risk currency classes

- `explicit_commencement_risk`: 1 documents
- `explicit_stale_consolidation`: 1 documents
- `explicit_transition_or_supersession`: 35 documents

## Required next actions

1. Complete `global_legal_corpus_v5`; do not infer runtime availability from this manifest audit.
2. Run `check_currency_payload_gate.py --require-complete` before cutover.
3. OCR and extraction-validate the 101 flagged documents, prioritising workflow-critical tax and parent-law sources.
4. Reclassify the broad `other_relevant_laws` queue using domain-specific categories, beginning with the latest promotion batch.
5. Resolve explicit commencement, historical-consolidation, repeal/transition, and amendment warnings with authoritative evidence.
6. Let scenario failures determine additional acquisition; do not resume collection by raw PDF target.

Machine-readable queues: `docs/evidence/corpus/post-promotion-quality-audit.json`.
