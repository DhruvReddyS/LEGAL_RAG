# Fast and Deep latency: before and after

Before: `baseline` recorded 2026-10-08T06:48:34.909537+00:00  
After: `after` recorded 2026-10-08T07:22:08.712958+00:00

- Before: commit `ff9abb9a3aaf`, collection `global_legal_corpus_v4` (49684 points), embedding on `mps`, load 2.21, 3.45, 4.04, swapouts/s 0.0, queue depth at start 0
- After: commit `8532d90d467a`, collection `global_legal_corpus_v4` (49684 points), embedding on `mps`, load 2.21, 2.43, 2.65, swapouts/s 0.0, queue depth at start 0

## Fast

21 runs before, 21 after.

### Read this first: was the host the same?

| Measure | Before | After | Delta |
|---|---:|---:|---:|
| Output tokens per query (p50) | 0 | 0 | +0.00 |
| Prompt tokens per query (p50) | 0 | 0 | +0.00 |

| Measure | Before (ms) | After (ms) | Delta |
|---|---:|---:|---:|
| End-to-end p50 | 94 | 35 | -58.88 (-62.6%) |
| End-to-end p95 | 177 | 166 | -11.63 (-6.6%) |
| End-to-end max | 213 | 718 | +504.96 (+236.7%) |
| Time to first useful output p50 | 94 | 35 | -58.88 (-62.6%) |
| Time to first useful output p95 | 177 | 166 | -11.63 (-6.6%) |

### Per stage, p50 then p95 (ms)

| Stage | Before p50 | After p50 | Before p95 | After p95 | p50 delta |
|---|---:|---:|---:|---:|---:|
| timing:api_overhead_ms | 0 | 0 | 0 | 0 | -0.01 (-100.0%) |
| timing:api_total_ms | 81 | 31 | 173 | 160 | -49.96 (-62.0%) |
| timing:embedding_ms | 0 | 0 | 129 | 106 | -0.02 (-66.7%) |
| timing:followed_chunk_count | 1 | 1 | 3 | 3 | +0.00 (+0.0%) |
| timing:persistence_ms | 5 | 4 | 22 | 10 | -1.71 (-31.7%) |
| timing:qdrant_ms | 20 | 13 | 49 | 45 | -7.16 (-35.9%) |
| timing:rag_service_ms | 60 | 25 | 165 | 156 | -35.02 (-57.9%) |
| timing:request_setup_ms | 2 | 1 | 8 | 2 | -0.83 (-40.3%) |
| timing:reranking_ms | 0 | 0 | 0 | 0 | +0.00 |
| timing:retrieval_enrichment_ms | 1 | 0 | 44 | 30 | -0.41 (-58.6%) |
| timing:retrieval_total_ms | 46 | 13 | 154 | 134 | -32.47 (-70.7%) |
| timing:safety_routing_ms | 0 | 0 | 0 | 0 | -0.05 (-50.0%) |
| timing:workflow_total_ms | 60 | 25 | 165 | 156 | -34.50 (-57.7%) |

### Answer quality

| Measure | Before | After | Delta |
|---|---:|---:|---:|
| Citations per query (mean) | 3.286 | 3.286 | +0.00 (+0.0%) |
| Distinct source titles (mean) | 3.286 | 3.286 | +0.00 (+0.0%) |
| Distinct source types (mean) | 2.143 | 2.143 | +0.00 (+0.0%) |
| Citations naming a section (mean) | 1.286 | 1.286 | +0.00 (+0.0%) |
| Citations with a source URL (mean) | 0.0 | 0.0 | +0.00 |
| Answer words (mean) | 357.429 | 357.429 | +0.00 (+0.0%) |
| Abstention rate | 0.0 | 0.0 | +0.00 |
| Published but graded insufficient | 0.1429 | 0.1429 | +0.00 (+0.0%) |
| LLM calls per query (mean) | 0.0 | 0.0 | +0.00 |
| LLM prompt tokens per query (mean) | 0.0 | 0.0 | +0.00 |
| LLM output tokens per query (mean) | 0.0 | 0.0 | +0.00 |

### Per query

| Query | Before p50 (s) | After p50 (s) | Cites before | Cites after | Words before | Words after | Abstained before | Abstained after |
|---|---:|---:|---:|---:|---:|---:|---|---|
| q01 | 0.05 | 0.03 | 4 | 4 | 387 | 387 | False | False |
| q02 | 0.08 | 0.11 | 4 | 4 | 426 | 426 | False | False |
| q03 | 0.17 | 0.04 | 4 | 4 | 436 | 436 | False | False |
| q04 | 0.10 | 0.03 | 4 | 4 | 463 | 463 | False | False |
| q05 | 0.11 | 0.03 | 0 | 0 | 18 | 18 | False | False |
| q06 | 0.09 | 0.03 | 3 | 3 | 348 | 348 | False | False |
| q07 | 0.13 | 0.08 | 4 | 4 | 424 | 424 | False | False |

## Deep

21 runs before, 21 after.

### Read this first: was the host the same?

| Measure | Before | After | Delta |
|---|---:|---:|---:|
| Decode rate (tokens/second, p50) | 14 | 23 | +8.40 (+58.2%) |
| Output tokens per query (p50) | 675 | 669 | -6.00 (-0.9%) |
| Prompt tokens per query (p50) | 7,965 | 6,903 | -1,062.00 (-13.3%) |

> **The host decoded 58% faster in the after run.** Deep latency is output tokens divided by this rate plus prefill, so the end-to-end deltas below are not attributable to the code change. Only figures that cannot move with throughput -- call counts, token counts, stage ordering, time to first output -- are safe to read as effects of the change.

| Measure | Before (ms) | After (ms) | Delta |
|---|---:|---:|---:|
| End-to-end p50 | 64,945 | 47,181 | -17,764.56 (-27.4%) |
| End-to-end p95 | 142,468 | 63,162 | -79,305.78 (-55.7%) |
| End-to-end max | 150,524 | 64,070 | -86,453.20 (-57.4%) |
| Time to first useful output p50 | 64,663 | 560 | -64,103.21 (-99.1%) |
| Time to first useful output p95 | 142,458 | 6,157 | -136,300.73 (-95.7%) |
| Time to first final output p50 | 64,663 | 46,680 | -17,982.89 (-27.8%) |
| Time to first final output p95 | 142,458 | 62,649 | -79,809.37 (-56.0%) |
| Time to first progress p50 | 549 | 551 | +2.20 (+0.4%) |

### Per stage, p50 then p95 (ms)

| Stage | Before p50 | After p50 | Before p95 | After p95 | p50 delta |
|---|---:|---:|---:|---:|---:|
| query_understanding | 0 | 0 | 6,514 | 5,656 | -0.04 (-12.9%) |
| reasoning | 52,399 | 36,769 | 116,480 | 46,220 | -15,630.02 (-29.8%) |
| response_generation | 1 | 1 | 3 | 2 | -0.71 (-48.3%) |
| retrieval | 86 | 76 | 963 | 157 | -10.35 (-12.0%) |
| retrieval_enrichment | 16 | 0 | 44 | 21 | -15.94 (-99.0%) |
| retry | 0 | — | 0 | — | — |
| role_context | 0 | 0 | 0 | 0 | -0.01 (-9.1%) |
| timing:query_understanding_ms | 8 | 7 | 6,529 | 5,669 | -1.45 (-17.4%) |
| timing:reasoning_0_ms | 51,450 | 36,781 | 64,002 | 46,232 | -14,669.65 (-28.5%) |
| timing:reasoning_1_ms | 60,253 | — | 64,377 | — | — |
| timing:response_generation_ms | 7 | 7 | 11 | 11 | -0.37 (-5.0%) |
| timing:verification_0_ms | 10,112 | 8,333 | 19,935 | 15,676 | -1,779.68 (-17.6%) |
| timing:verification_1_ms | 12,126 | — | 14,401 | — | — |
| timing:workflow_total_ms | 64,052 | 45,721 | 142,127 | 62,083 | -18,331.47 (-28.6%) |
| verification | 10,100 | 8,322 | 24,731 | 15,663 | -1,777.55 (-17.6%) |

### Answer quality

| Measure | Before | After | Delta |
|---|---:|---:|---:|
| Citations per query (mean) | 3.143 | 2.429 | -0.71 (-22.7%) |
| Distinct source titles (mean) | 2.429 | 1.857 | -0.57 (-23.5%) |
| Distinct source types (mean) | 1.762 | 1.571 | -0.19 (-10.8%) |
| Citations naming a section (mean) | 1.048 | 0.857 | -0.19 (-18.2%) |
| Citations with a source URL (mean) | 0.0 | 0.0 | +0.00 |
| Answer words (mean) | 247.381 | 221.714 | -25.67 (-10.4%) |
| Verification score (mean) | 0.532 | 0.572 | +0.04 (+7.5%) |
| Verified claims (mean) | 19.286 | 19.286 | +0.00 (+0.0%) |
| Unsupported claims per query (mean) | 5.619 | 5.0 | -0.62 (-11.0%) |
| Unadjudicated claims per query (mean) | 0.095 | 0.0 | -0.10 (-100.0%) |
| Abstention rate | 0.1429 | 0.1429 | +0.00 (+0.0%) |
| Published but graded insufficient | 0.0952 | 0.2857 | +0.19 (+200.1%) |
| LLM calls per query (mean) | 2.857 | 2.143 | -0.71 (-25.0%) |
| LLM prompt tokens per query (mean) | 8153.857 | 6875.0 | -1,278.86 (-15.7%) |
| LLM output tokens per query (mean) | 764.048 | 656.286 | -107.76 (-14.1%) |

### Per query

| Query | Before p50 (s) | After p50 (s) | Cites before | Cites after | Words before | Words after | Abstained before | Abstained after |
|---|---:|---:|---:|---:|---:|---:|---|---|
| q01 | 71.96 | 47.85 | 4 | 4 | 311 | 338 | False | False |
| q02 | 72.22 | 51.87 | 4 | 1 | 247/312 | 212 | False | False |
| q03 | 83.15 | 63.16 | 5 | 5 | 317 | 317 | False | False |
| q04 | 142.47 | 45.73 | 6 | 4 | 344 | 227 | False | False |
| q05 | 60.95 | 54.89 | 0 | 0 | 15 | 15 | True | True |
| q06 | 60.92 | 38.65 | 2 | 2 | 265 | 232 | False | False |
| q07 | 52.73 | 35.59 | 1 | 1 | 211 | 211 | False | False |

