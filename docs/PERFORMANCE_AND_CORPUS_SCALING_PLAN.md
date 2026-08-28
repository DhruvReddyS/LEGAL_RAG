# Performance, Scale, and Global Corpus Expansion Plan

Updated: 26 August 2026

This document is the execution plan after the accepted Tier 2 vertical slice.
It separates a low-latency research path from the slower multi-agent review
path and defines how new legal sources enter the corpus without weakening
provenance, currency, privacy, or retrieval quality.

## 1. Decision and service levels

The current 14B, sequential multi-agent path cannot reliably return a complete
verified answer within five seconds on the 24 GB Apple Silicon development
machine. Retrieval is only one component; serial query interpretation,
generation, independent verification, and retry account for most elapsed time.

The platform will expose two explicit modes:

| Mode | Intended use | Warm target | Safety boundary |
| --- | --- | ---: | --- |
| Fast research | provision lookup, procedure, definitions, first-pass questions | p95 complete response <= 5 s; p95 first token <= 0.8 s | short grounded answer, deterministic citation checks, no retry; escalate on low confidence |
| Deep review | case strategy, contradiction analysis, drafting, multi-source synthesis | stream immediately; completion measured separately | full multi-agent verification and bounded retry |

The five-second target is an acceptance target, not a claim about the current
build. It is accepted only after a repeatable load test passes on the declared
hardware profile.

## 2. Measured baseline

Observed development-machine timings from the accepted workflows:

| Stage/workflow | Observed elapsed time | Main issue |
| --- | ---: | --- |
| Warm BGE-M3 query embedding | about 0.9–1.0 s | large general-purpose embedding model |
| Cold BGE-M3 query embedding | about 5.8 s | model initialization/warm-up |
| BGE reranking, 10–20 candidates | about 5.3–5.6 s | long candidate text and large reranker |
| Accepted FIR legal query | 47.18 s | serial 14B generation and verification |
| FIR document drafting | 22.29 s | grounded generation |
| Defence analysis | 143.5 s | multi-stage reasoning and verification |
| Missing-dog general query with retry | 157.08 s | insufficient evidence followed by bounded retry |

Corpus baseline: 381 canonical documents, 17,426 pages, 25,517 chunks and
25,517 Qdrant points. See `INGESTION_ASSESSMENT.md` for extraction and storage
methodology.

## 3. P0 — measure before tuning

Implement first because an aggregate API time cannot identify regressions.

1. Add a request correlation ID and structured stage timings for authentication,
   query classification, cache, embedding, Qdrant, reranking, prompt assembly,
   model queue, time-to-first-token, generation, verification, persistence, and
   total duration.
2. Publish p50, p95, and p99 latency, throughput, token rate, error rate, retry
   rate, queue depth, cache-hit ratio, and resident memory. Separate cold and
   warm runs.
3. Add a reproducible benchmark set with short provision questions, procedural
   questions, multi-source questions, case-scoped searches, FIR drafting, and
   adversarial insufficient-evidence prompts.
4. Run at concurrency 1, 5, 10, and 25. Record exact hardware, models,
   quantization, corpus version, and configuration with every result.

Exit gate: one command produces machine-readable JSON and a human report, with
stage timings for every benchmark query.

## 4. P1 — under-five-second fast path

Execute in this order and compare retrieval quality after every change.

### 4.1 Remove unnecessary serial model calls

- Route simple provision/procedure questions with a deterministic classifier or
  compact local classifier. Do not use the 14B model merely to classify them.
- Generate the answer and citation plan in one compact-model call.
- Replace the second generative verifier on Fast mode with deterministic source
  existence, marker, page-range, corpus-tier, and claim-support checks. A small
  batched NLI model may be evaluated only if deterministic checks are
  insufficient.
- Disable retries in Fast mode. Low evidence must return a precise insufficient-
  evidence state and offer Deep review.
- Cap Fast answers at roughly 200–350 output tokens.

### 4.2 Reduce retrieval cost without losing recall

- Cache normalized query embeddings and final retrieval results by query,
  filters, authorised scope, corpus version, and model version.
- Benchmark candidate limits 8, 12, and 20. Rerank only the smallest candidate
  set that preserves the golden-query recall threshold.
- Feed the reranker a bounded 512–1,024-token passage window; restore the full
  chunk only after selection for citations.
- Benchmark a smaller reranker and a no-cross-encoder RRF threshold path for
  simple exact-provision queries.
- Precompute "provision cards" for frequently used Acts/sections: canonical
  title, current-status warning, bounded excerpt, and stable citation metadata.

### 4.3 Keep models resident and stream correctly

- Keep the Fast generation model, BGE embedder, and selected reranker warm.
- Use a compact 3B–7B quantized model for Fast mode after a quality/speed bakeoff;
  retain the 14B model for Deep mode.
- Add Server-Sent Events from FastAPI and incremental rendering in Next.js.
  Streaming improves time-to-first-token but is not counted as a five-second
  complete answer unless the final event arrives within the target.
- On the development Mac, compare Ollama with an Apple-Silicon-optimised MLX
  serving profile. On a production NVIDIA server, benchmark a continuous-
  batching server such as vLLM or SGLang rather than duplicating Ollama models
  across API workers.

Exit gate: the Fast benchmark passes p95 <= 5 seconds warm with citation and
retrieval acceptance unchanged. Deep mode remains functionally identical.

## 5. P2 — concurrency and production scale

The API, retrieval models, generation server, and ingestion workers must be
separate deployable processes.

1. Add Redis for query/result caches, rate limits, short-lived job state, and
   distributed locks. Never cache private results without role, owner, and case
   scope in the key.
2. Move OCR, corpus ingestion, case-document indexing, and report generation to
   a bounded background queue. Query traffic must not compete with ingestion.
3. Run multiple stateless FastAPI replicas for HTTP and database I/O. Do not
   load independent BGE/LLM copies inside every Uvicorn worker.
4. Place a dedicated inference service behind a bounded queue with backpressure,
   per-role quotas, cancellation, and timeouts.
5. Add Qdrant payload indexes for every production filter, collection aliases,
   snapshots, and restore drills. Tune HNSW/quantization only against the golden
   recall suite.
6. Add PgBouncer, verify SQL indexes with real query plans, and introduce read
   replicas only after database measurements justify them.
7. Add circuit breakers and graceful degradation: cached grounded answer,
   retrieval-only results, or explicit temporary-unavailable state.

Exit gate: the selected production profile passes the concurrency matrix with
no cross-case leakage, bounded memory, stable p95, and zero dropped audit events.

## 6. Global corpus expansion

New PDFs must not be copied directly into `data/legal_kb`. The intake path is:

```text
official source registry
  -> Bronze: immutable originals + fetch evidence
  -> Silver: extracted/OCR text + normalized metadata
  -> review queue: provenance, quality, currency, deduplication
  -> Gold: accepted versioned document
  -> shadow Qdrant collection
  -> retrieval/citation evaluation
  -> atomic alias promotion
```

### 6.1 Source priority

Expand domain by domain using official publishers and a recorded collection
policy. Priority order:

1. Central Acts, rules, regulations, gazette notifications, amendments, and
   commencement notifications.
2. Supreme Court and High Court judgments from official court repositories.
3. State Acts, rules, gazettes, police manuals, standing orders, and circulars.
4. Tribunal decisions, Law Commission reports, official practice directions,
   and government procedural guidance.
5. Commentary or secondary material only as a separately labelled, licensed
   tier; never present it as primary authority.

Before implementing a connector, verify the current official endpoint, terms,
robots policy, rate limits, licence, and permitted retention. Prefer an official
API, bulk release, sitemap, or feed over page scraping.

### 6.2 Required source registry

Record source ID, publisher, canonical URL/domain, jurisdiction, authority type,
language, access method, licence/terms evidence, crawl policy, refresh cadence,
last checked time, ETag/Last-Modified, download checksum, fetch status, reviewer,
and notes. Never silently replace an original file.

### 6.3 Quality and currency controls

- Validate MIME type, file signatures, malware scan result, checksum, and page
  readability before extraction.
- Exact deduplicate by SHA-256 and near-deduplicate by normalized text/minhash.
- Assign stable canonical document and legal-instrument IDs.
- Capture court, citation, bench, decision date, jurisdiction, Act, section,
  effective-from/to, amendment, repeal, successor, language, and official-source
  evidence with per-field confidence.
- Route low OCR confidence, missing pages, ambiguous titles, missing dates, and
  conflicting versions to human review.
- Build an amendment/supersession graph. Do not set `is_current=true` merely
  because a file is recent.

### 6.4 Incremental indexing and release

- Re-extract and re-embed only new or checksum-changed canonical documents.
- Version the chunker, embedding model, metadata schema, and corpus release.
- Build `global_legal_corpus_vN` as a shadow collection; validate counts,
  payloads, citations, and benchmark quality; then atomically move the serving
  alias. Keep the previous release for rollback.
- Add at least 20 reviewed golden questions per new jurisdiction/source family
  before promotion. Track recall@k, MRR/nDCG, citation correctness, current-law
  accuracy, abstention quality, and cross-scope isolation.

Exit gate per release: zero critical schema/provenance defects, every Gold item
has official-source evidence, retrieval thresholds pass, and rollback is tested.

## 7. Capacity planning from the present corpus

The current corpus averages about 67 chunks per canonical document and about
1.6 MiB of source PDF per document. If 1,000 broadly comparable documents are
added, the rough planning increment is about 67,000 chunks and 1.6 GiB of
original PDFs. Actual judgment collections can be much larger and must be
measured from a pilot sample.

Observed local storage ratios suggest roughly 0.5 GiB additional embedding
cache for 67,000 chunks. Qdrant planning from the current development volume is
approximately 9 GiB for that increment, but this is deliberately conservative:
the observed volume includes indexes, WAL, collection overhead, and historical
files. Run a 10,000-point pilot and measure compacted snapshots before procuring
production storage.

Keep at least three copies of accepted originals/metadata: primary object
storage, versioned backup, and a tested restore copy. Qdrant is rebuildable from
Gold artifacts, but snapshots shorten recovery.

## 8. Ordered execution backlog

1. Performance telemetry and benchmark harness.
2. Fast/Deep API contract and frontend streaming states.
3. Query/scope/corpus-version cache.
4. Retrieval candidate-window and reranker bakeoff.
5. Compact Fast model bakeoff and single-call grounded generation.
6. Five-second acceptance test and regression suite.
7. Background ingestion queue and query/worker process separation.
8. Source registry plus Bronze/Silver/Gold release tooling.
9. First official-source pilot: 100–250 documents in one legal domain.
10. Amendment tracker and current-law filter, followed by shadow-index promotion.

Manual actions expected: approve official source/terms policy, choose or provide
production inference hardware, pull the selected Fast model after benchmark
selection, install Rust/Cargo for Tauri acceptance, and assign a qualified human
reviewer for corpus currency and legal-quality gates.
