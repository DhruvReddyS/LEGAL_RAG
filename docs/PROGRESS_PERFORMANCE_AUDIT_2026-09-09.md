# Progress and Performance Audit

Date: 10 September 2026

## Executive result

- Estimated core-release completion: **about 85% overall**.
- Feature implementation: **about 95% of the declared release scope**.
- Broader PRD wishlist: **about 78%** if every listed built/deferred role feature is counted equally.
- Frontend verification today: **38/38 tests passed**, lint passed, production build passed.
- Backend verification today: **999/999 tests passed** against the live PostgreSQL, Qdrant, and MinIO dependencies.
- Best accepted Fast retrieval latency: **90.4 ms/query** over 61 questions.
- Best accepted Deep median latency: **53.0 s**; mean **61.9 s**; approximate p95 **122.1 s**.
- Current optimized four-question benchmark: **66.5 s mean**, down from **113.0 s** on the immediately preceding controlled run (**41% faster**).

The 85% overall figure is an engineering estimate, not a code-generated KPI. It weights implemented scope, automated verification, retrieval/answer quality, and operational consistency. A single percentage hides important differences, so the component scores below are more useful.

## Completion status

### Done

- Four role experiences: citizen, police, advocate, admin.
- JWT access/refresh authentication, cookie sessions, rotation and reuse detection.
- Database-driven RBAC and case ownership enforcement.
- Citizen Fast and Deep legal research, citations, abstention, safety screening, source inspection, uploads, feedback, and history.
- Police cases, private evidence, FIR drafting, investigation timelines, BNSS compliance, and currency checks.
- Advocate case corpus, two-sided defence analysis, authority mapping, specialist profiles, and currency checks.
- Admin user management, corpus statistics, ingestion progress, and audit log.
- PostgreSQL schema aligned to migration head `b2d5f8c1e4a7` after verifying the existing tables, indexes, and constraints.
- Qdrant hybrid dense+sparse retrieval and server-side RRF.
- MinIO object storage and durable PostgreSQL Deep jobs.
- Corpus ingestion, resumability, deduplication, OCR, structure-aware chunking, currency mapping, and evaluation harnesses.
- Frontend tests, lint, and production compilation pass on the current workspace.

### Still to do for release quality

- Complete and accept a fresh 61-question answer evaluation; the four-question latency gate is not a substitute for the full quality gate.
- Rebuild and smoke-test the final backend image after every release change; `/health/ready` is now the release readiness endpoint.
- Improve statutory ground coverage from **47.7%**.
- Improve currency correctness from **65.0%**.
- Raise governing-provision reach from **5/8 (62.5%)**.
- Improve citation accuracy among the first five displayed results from **63.8%**.
- Reduce citizen reading grade from approximately **14.1**.
- Expand the advocate evaluation slice beyond seven items.

### Deferred broader-scope features

- Citizen rights explainer as a distinct module.
- Citizen forum router.
- Drafting beyond FIR facts.
- Multilingual support.
- Upload redaction.
- State police manual coverage.
- Court-stage police tracking.
- Advocate debate room. It is intentionally parked because the estimated 25 sequential model calls would take 12-16 minutes on current hardware.

## Quality status

| Measure | Current accepted value | Interpretation |
|---|---:|---|
| Retrieval recall@5 | 92.7% | Strong topical retrieval |
| Retrieval recall@20 | 96.4% | Strong broad recall |
| Citation accuracy@5 | 63.8% | Too many displayed results are not ideal authorities |
| Governing provision reach | 62.5% (5/8) | Important current-law provisions remain unreachable for 3 core questions |
| Answer abstention correctness | 88.5% | Generally safe, but still has wrong answers/refusals |
| Ground coverage | 47.7% | Published answers omit more than half of authored statutory grounds on average |
| Currency correctness | 65.0% | Current/repealed-law disclosure needs work |
| Unsupported published claims | 0 | Core grounding invariant is holding |

## Timing inventory

### Retrieval

| Operation | Measured time | Notes |
|---|---:|---|
| Hybrid retrieval | 90.4 ms/query | 61-question v3 evaluation |
| Dense-only retrieval | 99.2 ms/query | Older ablation set |
| Sparse-only retrieval | 84.0 ms/query | Older ablation set |
| Hybrid under mixed load | 79.8 ms mean, 92.9 ms p95 | Three Fast requests while one Deep job ran |
| Qdrant portion under mixed load | 16.9-52.9 ms | Query embedding was cached in this run |
| Citation following | approximately 6-18 ms | Deterministic extra Qdrant lookup on measured core questions |

Retrieval is not the main latency problem.

### Reranking

| Mode | Time/query | R@1 | R@5 |
|---|---:|---:|---:|
| Hybrid, no cross-encoder | 90.7 ms | 69.0% | 83.3% |
| Cross-encoder reranked | 5,125.5 ms | 64.3% | 83.3% |

Reranking was about **56x slower**, reduced R@1, and did not improve R@5. It is correctly disabled by default. Do not re-enable it without a new corpus-specific evaluation.

### Deep RAG

Accepted 61-question run:

- median: **53.0 s**
- mean: **61.9 s**
- approximate p95: **122.1 s**
- minimum: **22.8 s**
- maximum: **175.3 s**
- complete evaluation wall time: **3,776.7 s = 62.9 minutes**

Another full run recorded before the accepted baseline took:

- median: **102.6 s**
- mean: **129.4 s**
- approximate p95: **246.3 s**
- maximum: **368.6 s**
- total: **7,893.4 s = 131.6 minutes**

Earlier interrupted rerun:

- completed: **9/61 = 14.8%**
- median: **120.2 s**
- mean: **127.2 s**
- range: **83.7-199.4 s**
- time already spent: **19.1 minutes**
- projected total at the current mean: **about 129 minutes**
- partial abstention correctness: **7/9 = 77.8%**

Do not use the partial 9-question result as the new baseline.

Current optimized four-question run:

- mean: **66.5 s**, down from **113.0 s** (**41%**)
- citizen range: **59.3-85.0 s**
- retrieval range: **0.23-0.59 s**
- reasoning range: **48.9-65.7 s**
- verification range: **7.0-18.7 s**
- final deterministic response assembly: approximately **1 ms**
- answer length remained within **4-37 words** of the preceding run
- citations changed from **5/5/5/2** to **5/4/5/2**

### Deep stage breakdown

A controlled four-question run after the compact-verdict optimization measured:

| Stage | Mean | Share of total |
|---|---:|---:|
| Retrieval | 0.446 s | 0.67% |
| LLM reasoning/draft generation | 54.1 s | 81.3% |
| LLM claim verification | 11.9 s | 17.9% |
| Final response assembly | 1 ms | effectively 0% |
| Total | 66.5 s | 100% |

Important naming detail: `response_generation` is not an LLM call in the current graph. It formats already verified claims. The expensive final-answer writing occurs in the `reasoning` LLM stage.

### Evaluation time

- One v3 hybrid retrieval evaluation: approximately **5.5 seconds** for 61 questions.
- Older dense+sparse+hybrid+reranked ablation: **259.2 seconds (4.3 minutes)**; reranking alone consumed **246.0 seconds**.
- Accepted full answer-quality evaluation: **62.9 minutes**.
- Slower full answer-quality run: **131.6 minutes**.

### Queue and concurrency

In an older two-job stress run:

- first Deep job service time: **333.0 s**
- second job queue wait: **333.2 s**
- second job service time: **209.9 s**
- second job end-to-end time: **543.1 s**

This happens because Ollama generation concurrency is intentionally one. It protects a 24 GB machine from running multiple large model contexts at once, but concurrent Deep users wait serially.

### Other feature timings

The project currently does not have accepted per-feature benchmark files for authentication, case CRUD, uploads, OCR, FIR drafting, defence analysis, document analysis, admin queries, or individual PostgreSQL operations. HTTP middleware records total request duration and the RAG graph records stage timings, but these features need the same benchmark treatment before exact values can be claimed.

## Why Deep mode is slow

### 1. Local 14B model decode speed

The measured 14B model generates about **13.6-14.4 tokens/s** and prefills at approximately **243-367 tokens/s**. A 1,000-token structured result can therefore spend around 70 seconds on output decoding alone.

### 2. At least two sequential LLM calls

Deep mode normally performs one reasoning call and one verification call. Verification cannot start until reasoning finishes. Missing/invalid structured output can trigger another attempt, and insufficient support can trigger a bounded retrieval/reasoning retry.

### 3. Large prompts

Reasoning can include eight evidence excerpts of up to 1,800 characters. Verification now caps each source premise at 1,800 characters. Long legal passages still increase prefill time and model memory use.

### 4. Large structured output allowance

Reasoning now uses a 1,200-token output budget and verification uses a small claim-count-based budget. The repository's own experiment raising the claim cap from 10 to 18 changed median latency from 53 seconds to 154 seconds without improving ground coverage.

### 5. Verification duplicates work

The verifier still evaluates claim/source pairs sequentially after reasoning, but now emits only positional `yes`, `partial`, or `no` verdicts. Removing repeated indexes and reasons reduced mean verification time from 42.3 seconds to 11.9 seconds.

### 6. Model and memory state vary

The accepted evaluation recorded heavy swap growth, from 4.17 GB to 17.7 GB. The current optimized run completed with about 6.2 GB still in swap from earlier model experiments and the 14B model warm in Ollama. A cold request will still pay model load/warmup cost. Serving while ingesting is especially harmful because the 14B model, BGE-M3, optional reranker, Docker VM, and ingestion embedding copy exceed comfortable memory headroom.

### 7. Single-generation queue

Concurrency one means stable single-request behavior but linear queue delay under multiple Deep requests. Raising concurrency on the same 24 GB host is likely to cause memory compression/swap and make every request slower.

### 8. Benchmark/runtime consistency

The schema is now stamped at migration head and the rebuilt container uses `/health/ready`. Preserve this consistency by rebuilding the image and recording its revision before every accepted benchmark.

## Lowest-latency plan

### Priority 0: make measurements trustworthy — current release gate completed

1. Rebuild/recreate the backend container from the current commit.
2. Restore a dedicated backend test environment with development requirements.
3. Benchmark on an idle machine with no ingestion, no second evaluation, and no competing Deep job.
4. Record commit hash, model hash, context, prompt fingerprints, memory before/after, token counts, queue wait, prefill, decode, and stage timings.
5. Run one cold request separately, then measure warm requests.

Expected effect: removes false regressions and makes subsequent changes comparable.

### Priority 1: use Fast mode whenever safe

Keep `auto` as the default and send focused authority questions to Fast mode. Fast currently returns in roughly **80-100 ms**, which is 500-1,500 times faster than current Deep runs. Use Deep only for multi-issue, case-scoped, comparative, drafting, or evidence-analysis questions.

Expected user-visible target:

- simple legal lookup: **under 250 ms warm**
- ordinary grounded summary without claim-by-claim LLM verification: **under 2 seconds** if assembled deterministically
- Deep verified analysis on current 14B hardware: realistically **30-60 seconds**, not sub-second

### Priority 2: keep reranking off

This saves about five seconds per query and improves or preserves measured quality.

### Priority 3: keep Ollama warm — implemented

The client now sends `keep_alive=30m`, and startup warms BGE-M3 and the actual Ollama generation model in parallel. Continue separating cold-start metrics from warm latency.

Expected effect: removes model-load delay on the first Deep request.

### Priority 4: dynamic output budgets — implemented for the current Deep path

Use query-specific budgets instead of a universal 1,800-token structured ceiling:

- simple direct question: 4-6 claims, roughly 500-800 output tokens
- enumerated statutory question: up to 10 claims, roughly 900-1,200 tokens
- case strategy: larger budget only when required

Do not globally raise the claim cap; that experiment already caused a 3x slowdown and quality regressions.

Expected effect: potentially 20-50 seconds saved on verbose Deep answers, subject to answer-quality gates.

### Priority 5: reduce verification cost safely — compact verdicts implemented

Test these separately:

- ask for one terse verdict per claim and omit verbose reasons on `yes` results;
- verify one claim against its selected evidence set instead of emitting a verdict for every claim-source pair;
- deterministically accept exact/statutory extracts and send only synthesized or weakly supported claims to the LLM verifier;
- use a dedicated faster verifier model, but accept it only if unsupported claims remain zero and abstention/currency metrics do not regress.

Measured effect: mean verification fell from roughly **42.3 seconds to 11.9 seconds** on the controlled four-question benchmark.

### Priority 6: evaluate an 8B-class model

The measured 4B model reaches **32.9-44.7 tokens/s**, about 2.5-3x the 14B decode rate, but the project correctly refuses to treat an unvalidated small model as safe legal reasoning. Evaluate a strong 8B-class quantized model for reasoning and/or verification against all quality gates. Do not switch based on speed alone.

Expected effect: a validated 8B model could plausibly reduce Deep latency substantially while fitting memory better. The exact result must be measured.

### Priority 7: stage-specific context sizes

The client currently uses a fixed 16,384-token context for all calls. Measure whether query understanding and verification fit safely in 8,192 tokens. A smaller context lowers KV-cache memory and may reduce pressure, although prompt length and output decoding remain the dominant costs.

### Priority 8: scale out, not up, for multiple users

For concurrent Deep users, add another Ollama host or GPU-backed generation service. Keep one generation at a time per 24 GB host. More API workers will not fix an LLM-bound pipeline.

## Recommended acceptance targets

| Area | Next target |
|---|---:|
| Fast warm p95 | <250 ms |
| Deep warm p50 | <45 s initially, then <30 s if quality holds |
| Deep p95 | <90 s |
| Unsupported claims | 0 |
| Recall@5 | >=92% |
| Citation accuracy@5 | >=75% |
| Provision reach | >=7/8 |
| Ground coverage | >=65% |
| Currency correctness | >=90% |
| Backend tests | all pass on current commit |
| Frontend tests/build/lint | all pass |

## Evidence used

- `README.md`
- `docs/PRD.md`
- `docs/NEXT_STEPS.md`
- `docs/evidence/quality-baseline.json`
- `docs/evidence/answer-quality-baseline.json`
- `docs/evidence/provision-reach-baseline.json`
- `docs/evidence/eval-global_legal_corpus_v3-20260906T113035Z.json`
- `docs/evidence/deep-answers-after.json`
- `docs/evidence/phase1-mixed-load-run-09.json`
- `docs/evidence/phase1-queued-deep-run-01.json`
- `docs/evidence/ollama-throughput-m5pro-14b-ctx16384.json`
- `docs/evidence/ollama-throughput-m5pro-4b-ctx8192.json`
- current source, migration state, running services, frontend verification, and machine-memory checks
