# v3 versus v4 retrieval activation review

Date: 3 October 2026

## Decision

**Keep `global_legal_corpus_v3` active. Do not activate v4 yet.**

Both evaluations use `golden_set_v3.json`. The v4 build is complete (400 documents,
26,210 chunks, zero checkpoint failures), but the existing retrieval evidence does
not meet the no-regression activation condition.

## Summary comparison

| mode | metric | v3 | v4 | delta |
|---|---|---:|---:|---:|
| dense | recall@5 | 0.9091 | 0.9273 | +0.0182 |
| dense | MRR | 0.7346 | 0.7305 | -0.0042 |
| dense | citation accuracy@5 | 0.5712 | 0.5773 | +0.0061 |
| sparse | recall@5 | 0.8909 | 0.8727 | -0.0182 |
| sparse | MRR | 0.7211 | 0.7117 | -0.0094 |
| sparse | citation accuracy@5 | 0.5667 | 0.5818 | +0.0152 |
| hybrid | recall@5 | 0.9273 | 0.8727 | -0.0545 |
| hybrid | MRR | 0.7447 | 0.7243 | -0.0204 |
| hybrid | citation accuracy@5 | 0.5712 | 0.5818 | +0.0106 |
| reranked | recall@5 | 0.9273 | 0.8727 | -0.0545 |
| reranked | MRR | 0.7447 | 0.7243 | -0.0204 |
| reranked | citation accuracy@5 | 0.5667 | 0.5773 | +0.0106 |

Abstention accuracy falls from 0.6667 to 0.5000 in every evaluated mode. Latency is
effectively unchanged for dense and reranked retrieval and slightly higher for sparse
and hybrid retrieval.

## Interpretation

V4 improves dense recall@5 and citation accuracy, but those gains do not offset the
hybrid/reranked recall and MRR regressions or the lower abstention accuracy. Because
hybrid/reranked retrieval is the operationally important path, activating v4 would
violate the requested no-regression rule.

## Required before reconsidering activation

1. Reconcile the 419-row physical inventory with the 438-row canonical registry.
2. Correct metadata/classification defects in the 19 additions.
3. Add family, civil, property/AP, labour/welfare, and missing-source test questions.
4. Re-run v3 and the expanded v4 candidate against the same golden set and settings.
5. Investigate the hybrid/reranked per-query regressions and abstention failures.
6. Activate only after the expanded v4 equals or exceeds v3 on the agreed critical
   metrics and passes criminal-law regression tests.

## Rollback posture

No configuration change was made. `.env` and `.env.example` continue to select
`global_legal_corpus_v3`; both v3 and v4 collections remain available.

Evidence files:

- `docs/evidence/retrieval-eval-v3-current.json`
- `docs/evidence/retrieval-eval-v4.json`
- `data/legal_kb/logs/ingestion_checkpoint.global_legal_corpus_v3.json`
- `data/legal_kb/logs/ingestion_checkpoint.global_legal_corpus_v4.json`
