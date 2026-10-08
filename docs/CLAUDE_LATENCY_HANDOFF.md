# Claude handoff: measured Fast and Deep latency optimisation

Date: 2026-10-08

## Objective

Reduce response latency in both Fast/Quick and Deep modes without sacrificing
retrieval recall, legal depth, citation precision, claim verification,
abstention behaviour, privacy, or answer usefulness. Deep mode must remain the
more insightful research mode; do not manufacture a speed improvement by
cutting its evidence or claim budgets.

## Scope and ownership boundary

Work only on measured query-path performance and directly related tests or
observability. Do not edit source manifests, `candidate_imports/`, corpus
promotion policy, `data/legal_kb/**`, or run ingestion. Codex owns the current
collection batch while this task is active.

Read first:

- `docs/PRODUCT_ROADMAP.md`
- `docs/NEXT_STEPS.md`
- `docs/evidence/README.md`
- the current Fast and Deep service implementations and their tests

Known baseline/context:

- A previously documented Deep p50 fell from 102.6 s to 53.0 s after the
  absolute-sufficiency fix.
- Configuration targets are currently 5,000 ms for Fast and 300,000 ms for
  Deep.
- Retrieval already contains a query-embedding cache and separate embedding
  and reranking semaphores.
- Fast deliberately skips cross-encoder reranking and the LLM research chain.
- Measurements made while corpus ingestion is running are invalid because the
  machine swaps heavily. Benchmark only when idle.

## Required work

1. Establish reproducible before numbers for Fast and Deep using the same
   corpus, model configuration, and query set. Record end-to-end p50/p95,
   time-to-first-useful-output where applicable, and stage-level timings.
2. Profile before changing behaviour. Investigate cold start and warm-up,
   embedding-cache effectiveness, model-call serialization/concurrency,
   redundant LLM calls, prompt/context assembly, safe retrieval/result caches,
   cancellation, streaming, and progress reporting.
3. Implement only improvements supported by measurements. Prefer eliminating
   duplicated work and waiting over reducing evidence quality.
4. Add or update regression tests. Compare answer quality before and after,
   including citation coverage, citation correctness, unsupported-claim rate,
   and abstention on insufficient evidence.
5. Produce a short evidence report containing the environment, corpus/version,
   query set, before/after p50 and p95, per-stage deltas, quality deltas, tests,
   and remaining bottlenecks.

## Optional feature if evidence supports it

For Deep mode, add progressive status or streaming of verified sections so the
user sees useful, source-backed progress earlier. Never stream unverified legal
claims as final answers; preserve the final verification and citation gates.

## Acceptance gates

- Both modes have comparable before/after measurements on an idle machine.
- No statistically or substantively meaningful regression in retrieval or
  answer-quality gates.
- Fast remains genuinely fast and concise.
- Deep remains comprehensive and more insightful than Fast.
- No corpus mutation or ingestion is performed by this task.
