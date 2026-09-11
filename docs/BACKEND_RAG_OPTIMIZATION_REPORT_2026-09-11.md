# Backend and RAG Optimization Report

Date: 11 September 2026

## 1. Executive assessment

The backend is not slow everywhere. The two answer modes have very different
performance profiles:

- Fast mode retrieval is already fast: the best accepted 61-question run is
  90.4 ms per query.
- Deep mode is slow because it runs a local 14B language model at least twice
  in sequence. Retrieval is less than 1% of the measured Deep duration.
- The cross-encoder reranker must remain disabled. It cost about 5.1 seconds
  per query and reduced R@1 in the measured ablation.
- Retrieval recall is strong, but displayed citation precision, governing
  provision reach, ground coverage, and current-law disclosure still require
  work.
- It is unsafe to promise a strong legal answer for every question. When the
  corpus lacks the governing material, the correct behavior is a clear
  abstention plus a useful explanation of what source is missing.

The best strategy is therefore not "make every question Deep." It is:

1. Return focused source answers through Fast mode.
2. Route only genuinely analytical work to Deep mode.
3. Improve authority selection and corpus coverage without adding a slow
   reranker.
4. Reduce Deep output and verification work only behind quality gates.
5. Scale generation workers separately from the API and retrieval services.

## 2. Current backend process

```text
Browser / Next.js
      |
      | POST /chat/query with JWT or secure cookie
      v
FastAPI authentication and RBAC
      |
      v
Load/create chat session -> persist user message
      |
      v
Citizen safety screen -> document context -> adaptive mode router
      |
      +-----------------------+
      |                       |
      v                       v
 FAST MODE                 DEEP MODE
 deterministic             LangGraph workflow
 hybrid retrieval          query understanding
 evidence gate             hybrid retrieval
 citation formatting       citation following
      |                     reasoning LLM
      |                     verification LLM
      |                     deterministic publication
      +-----------+-----------+
                  |
                  v
 Persist answer, citations, trace and audit log in PostgreSQL
                  |
                  v
 JSON response -> React renders answer, citations, confidence and timings
```

### Data systems

- PostgreSQL stores users, roles, sessions, messages, cases, jobs, feedback,
  and audit records.
- Qdrant stores dense and sparse vectors plus legal-source metadata.
- MinIO stores uploaded source files and private case documents.
- BGE-M3 creates dense and sparse query embeddings.
- Ollama serves `qwen3-14b-16k:latest` for Deep reasoning and verification.

## 3. Current timing inventory

These are accepted repository measurements. They are not estimates from code.

### Fast mode

| Stage or operation | Current measured value | Interpretation |
|---|---:|---|
| Hybrid retrieval, 61 questions | 90.4 ms/query | Already strong |
| Hybrid retrieval under mixed load | 79.8 ms mean, 92.9 ms p95 | Deep work did not destroy Fast latency |
| Qdrant portion under mixed load | 16.9-52.9 ms | Query embedding was cached |
| Citation following | about 6-18 ms | Cheap deterministic authority lookup |
| Cross-encoder reranking | 5,125.5 ms/query | Disabled because it was slower and worse |

The existing configured Fast target is 5,000 ms, which is too loose for
performance management. The operational target should be 250 ms warm p95.

### Fresh rebuilt API samples on 11 September

The rebuilt compose backend reported CPU embedding and CPU reranking. These
single-question samples validate the endpoint and timing instrumentation; they
are not a replacement for the 61-question acceptance benchmark.

| Sample | Embedding | Qdrant | RAG service | API total |
|---|---:|---:|---:|---:|
| Cold query embedding | 467.72 ms | 119.00 ms | 602.79 ms | 613.24 ms |
| Warm cached sample 1 | 0.05 ms | 32.90 ms | 38.37 ms | 43.89 ms |
| Warm cached sample 2 | 0.02 ms | 53.92 ms | 58.73 ms | 68.23 ms |

All three returned three citations with confidence 0.829 and no cross-encoder
time. In the first warm sample, request setup was 1.91 ms, safety/routing was
0.37 ms, persistence was 3.23 ms, and residual API overhead was 0.01 ms. This
confirms that the Fast endpoint itself and PostgreSQL persistence are not the
bottleneck. Cold CPU query embedding is the dominant cold-path cost.

### Deep mode, accepted full run

| Metric | Current measured value |
|---|---:|
| Minimum | 22.8 s |
| Median | 53.0 s |
| Mean | 61.9 s |
| Approximate p95 | 122.1 s |
| Maximum | 175.3 s |
| 61-question wall time | 62.9 minutes |

### Deep mode, controlled four-question stage breakdown

| Stage | Mean | Share |
|---|---:|---:|
| Role/context setup | about 0.01 s | less than 0.1% |
| Query understanding | about 0.001 s | less than 0.1% |
| Retrieval | 0.45-0.66 s | about 0.7-1.0% |
| Reasoning/draft LLM | 54.1 s | 81.3% |
| Verification LLM | 11.9 s | 17.9% |
| Final answer formatting | about 0.001-0.002 s | effectively 0% |
| Total | about 66.5 s | 100% |

`response_generation` is deterministic formatting, not another LLM call.
The expensive final wording is produced inside the reasoning stage.

### Evaluation duration

| Evaluation | Current measured duration |
|---|---:|
| 61-question retrieval evaluation | about 5.5 s |
| Retrieval plus cross-encoder ablation | 259.2 s |
| Accepted 61-question answer evaluation | 62.9 minutes |
| Slower historical answer evaluation | 131.6 minutes |

### Queue behavior

Ollama generation concurrency is one. In the recorded two-job stress run:

- Job 1 service time: 333.0 s.
- Job 2 queue wait: 333.2 s.
- Job 2 service time: 209.9 s.
- Job 2 end-to-end time: 543.1 s.

This protects the 24 GB machine from concurrent 14B contexts, but it cannot
serve several Deep users with low latency.

### Other backend features

There is not yet accepted stage-level evidence for login, refresh, case CRUD,
file upload, OCR, FIR drafting, defence analysis, admin queries, or individual
PostgreSQL operations. Previously, middleware exposed only whole-request time.
The chat API now additionally reports:

- `request_setup_ms`
- `safety_routing_ms`
- `rag_service_ms`
- `persistence_ms`
- `api_overhead_ms`
- `api_total_ms`

This instrumentation is implemented, but new live values must be collected
after the stack is running.

## 4. Current quality statistics

| Measure | Current accepted value | Desired release target |
|---|---:|---:|
| Recall@5 | 92.7% | at least 92% |
| Recall@20 | 96.4% | at least 96% |
| Citation accuracy@5 | 63.8% | at least 75% |
| Citizen citation accuracy@5 | about 69.9% | at least 80% |
| Governing-provision reach | 5/8 accepted baseline; 8/8 measured after this change | 8/8 on the core set |
| Answer abstention correctness | 88.5% | at least 90% |
| Ground coverage | 47.7% | at least 65% |
| Currency correctness | 65.0% | at least 85% |
| Unsupported published claims | 0 | must remain 0 |

Recall and precision are different:

- Recall asks whether a useful source appears somewhere in the result window.
- Citation precision asks how many displayed sources are actually good sources
  for this exact question.

The system has high recall but only moderate citation precision. Fetching more
documents alone will not solve this; publication must select better authorities.

## 5. Why it takes so much time

### 5.1 Local model decode speed

The 14B model produces about 13.6-14.4 output tokens per second. A long
1,000-token JSON draft can therefore spend around 70 seconds decoding. Prompt
prefill is faster, about 243-367 tokens per second, but large legal passages
still add seconds and consume memory.

### 5.2 Sequential model calls

Reasoning must finish before verification begins. Deep mode normally makes two
model calls. Invalid structured output, omitted verifier decisions, or an
insufficient first pass can cause extra calls.

### 5.3 Output size

The reasoning ceiling is 1,200 tokens and up to 10 claims. Increasing the claim
cap to 18 was already tested: median latency rose from 53 seconds to 154 seconds
without improving ground coverage. A larger answer budget is not automatically
a better answer.

### 5.4 Prompt size

Reasoning can include eight excerpts of up to 1,800 characters. Verification
can read another 1,800 characters for each cited source. This is bounded, but
legal text is still large.

### 5.5 Memory pressure

Accepted runs recorded swap growth up to 17.7 GB. Running corpus ingestion,
embeddings, Docker, BGE-M3, and the 14B model together reduces memory headroom.
Swap makes model inference inconsistent and much slower.

### 5.6 Single generation worker

Concurrency one prevents memory collapse on the laptop. It also means the
second Deep request waits for the first. Raising concurrency on the same 24 GB
machine is likely to make both requests slower.

## 6. Optimization plan

The status column distinguishes completed work from proposals.

### Priority 0: measurement and correctness gates

| Change | Status | Expected effect |
|---|---|---|
| Detailed RAG-stage telemetry | Implemented | Identifies model, queue, prefill and decode cost |
| API setup/routing/persistence telemetry | Implemented on 11 Sep | Identifies non-RAG backend cost |
| Retrieval-enrichment telemetry | Implemented on 11 Sep | Separates search from citation/intent enrichment |
| Cold and warm benchmarks recorded separately | Required | Removes misleading startup regressions |
| Record commit, model, corpus and prompt fingerprints | Mostly implemented | Makes runs comparable |
| Run retrieval, answer, provision and safety gates after tuning | Required | Prevents speed improvements from reducing safety |

### Priority 1: improve Fast-mode quality without slowing it

1. Keep server-side dense+sparse RRF and the embedding cache.
2. Keep cross-encoder reranking disabled.
3. Add deterministic query-to-law bridges for relations the corpus cannot
   discover lexically. The first three are implemented in Fast and Deep mode:
   - constitutional arrest right -> BNSS section 47 implementation;
   - default bail -> BNSS section 187 proviso;
   - theft concept -> BNS section 303.
4. Give exact current statutes and directly controlling sources priority when
   they match the user's issue.
5. Keep one or two explanatory judgments or official guides after the primary
   law instead of displaying several near-duplicate passages.
6. Cache bounded term-frequency lookups for repeated queries, with collection
   version in the cache key.

Target after measurement:

- warm Fast p50 under 120 ms;
- warm Fast p95 under 250 ms;
- citation accuracy@5 at least 75%;
- core provision reach 8/8;
- no recall@5 regression below 92%.

The eight-question provision gate now reaches 8/8, up from 5/8. The three
former misses are reached as follows:

- default bail -> BNSS section 187 at rank 9;
- theft current law -> BNS section 303 at rank 10;
- communication of arrest grounds -> BNSS section 47 at rank 9.

A deployed Fast smoke query for communication of arrest grounds placed BNSS
section 47 first, followed by three relevant judgments. It measured 627.29 ms
on a cold CPU embedding path, including 504.62 ms base retrieval and 105.03 ms
exact-law enrichment. The response remained explicitly unverified because Fast
mode does not run the Deep claim verifier.

### Priority 2: reduce Deep reasoning time

Test one variable at a time:

1. Use a smaller output budget for genuinely simple Deep requests. Preserve
   the 1,200-token budget for enumerations and case analysis.
2. Reduce duplicate legal metadata in the model prompt while retaining title,
   section, currency, pages, and source labels.
3. Select evidence by authority and issue coverage before prompting. More
   passages should be included only when they add a new ground or exception.
4. Detect exact statutory extraction questions and answer them through a
   deterministic grounded-summary path instead of the full reasoning model.
5. Trial a faster generation model only as an A/B test. Accept it only if all
   quality and safety gates pass.

Realistic target on the current 14B laptop setup:

- Deep warm p50 below 45 seconds first;
- Deep warm p95 below 90 seconds;
- 30 seconds p50 is possible only with shorter output, fewer model calls, a
  faster validated model, or stronger hardware.

Sub-second Deep verified generation is not realistic on this hardware.

### Priority 3: reduce verification cost safely

Compact positional verdicts have already reduced mean verification from about
42.3 seconds to 11.9 seconds on the controlled set. Next experiments:

1. Deterministically accept only exact verbatim statutory extracts with exact
   source location and no synthesis.
2. Send synthesized, conditional, and weak claims to the LLM verifier.
3. Verify each unique claim against its selected evidence set once, rather
   than duplicating equivalent claim-source pairs.
4. Trial a smaller dedicated verifier model.

Hard acceptance rules:

- unsupported published claims remain zero;
- abstention correctness does not fall;
- currency correctness does not fall;
- missing verifier verdicts are never published as supported.

### Priority 4: scale Deep mode

For multiple users, scale the generation tier, not PostgreSQL first:

```text
FastAPI replicas
      |
      +--> PostgreSQL connection pool
      +--> Qdrant
      +--> MinIO
      |
      v
Durable Deep-job queue
      |
      +--> GPU/Ollama worker 1, concurrency 1
      +--> GPU/Ollama worker 2, concurrency 1
      +--> GPU/Ollama worker N, concurrency 1
```

Recommended production shape:

- stateless FastAPI replicas behind a load balancer;
- PostgreSQL pool sized below the database connection limit;
- durable jobs retained in PostgreSQL or moved to a dedicated queue when load
  justifies it;
- one 14B generation at a time per worker/GPU;
- horizontal Deep workers for throughput;
- separate ingestion workers so ingestion never competes with user answers;
- backpressure, queue position, cancellation, and per-user limits;
- streaming progress even when the final structured answer cannot be streamed.

## 7. Improving precision, accuracy and detail

### Better source selection

Use a deterministic authority policy after retrieval:

1. Exact current statutory provision.
2. Binding or highly authoritative judgment directly addressing the issue.
3. Official government guidance explaining the procedure.
4. Secondary explanatory material only when primary authority is absent.

Do not apply this as a universal source-type boost. A precedent question may
correctly require a judgment ahead of a statute. Authority ranking must depend
on query intent.

### Better citations

Each displayed citation should expose:

- source title and type;
- act and section when available;
- court and decision date for judgments;
- page range;
- official source URL;
- exact supporting excerpt;
- current, superseded, repealed, or unknown currency status;
- why the source supports the displayed claim;
- verification status.

The current Deep citation schema already carries most of these fields. The next
quality improvement is exact claim-to-excerpt highlighting and a short
`why_relevant` explanation produced deterministically from the matched section
or verified claim, not an unsupported model statement.

### Strong answers without fabrication

A strong answer should include, when supported:

1. Direct answer in plain language.
2. Current legal rule and exact provision.
3. Conditions or grounds, each as a separate point.
4. How the rule applies to the facts the user actually supplied.
5. Practical next steps.
6. Exceptions, missing facts, deadlines, and uncertainty.
7. Detailed citations next to each claim.

When evidence is incomplete, the answer should say exactly what was found,
what was not found, and what official material is needed. This is more useful
and safer than a generic "insufficient evidence" message.

## 8. Corpus expansion required

The active corpus is broad in criminal law and constitutional rights but still
has known topic and sub-topic gaps. The downloaded Phase A source set is a
candidate set, not yet part of the active corpus.

Before ingestion:

1. OCR the scanned advisory.
2. Extract text and validate page counts.
3. Verify title, issuer, date, jurisdiction, source URL, and current-law status.
4. Deduplicate against the active corpus.
5. Chunk statutes by section and procedures by heading/list structure.
6. Add retrieval questions and expected authority predicates.
7. Ingest into a versioned staging collection.
8. Run retrieval, provision, answer, safety, and latency evaluations.
9. Promote the collection only if the quality gates pass.

Highest-value additional source families:

- current central statutes and official rules;
- current state rules, police manuals and citizen charters;
- procedural forms and official filing instructions;
- Supreme Court and selected High Court landmark/current decisions;
- Legal Services Authority guides and scheme documents;
- women, child, disability, labour, consumer, cybercrime, tenancy, family,
  senior-citizen, and welfare procedure material;
- official amendment and commencement notifications;
- statute concordances and explicit right-to-implementation mappings.

More data is helpful only when metadata, authority, currency, and evaluation
coverage improve with it. Uncurated volume can reduce citation precision.

## 9. Benchmark protocol

Use the same protocol for every claimed improvement:

1. Stop ingestion and unrelated model work.
2. Record commit, corpus collection, model and machine memory.
3. Run one cold request and label it cold.
4. Warm BGE-M3 and Ollama.
5. Run the fixed retrieval set.
6. Run the fixed provision-reach set.
7. Run the small Deep latency set for iteration.
8. Run the complete answer-quality set before acceptance.
9. Compare p50, p95, recall, precision, ground coverage, currency,
   abstention, unsupported claims, token counts, and queue wait.
10. Revert a change that is faster but fails a hard quality gate.

## 10. Best achievable outcome

### On the current laptop

- Fast: 80-250 ms warm for focused questions.
- Deterministic grounded summary: potentially under 2 seconds.
- Deep 14B: about 30-60 seconds for ordinary warm requests after careful
  output/prompt reduction.
- Concurrent Deep users: queueing remains unavoidable with one model worker.

### With production GPU workers

- Fast remains in the low hundreds of milliseconds.
- Deep latency can fall substantially with a faster validated inference engine
  and GPU, but exact numbers require benchmarking the selected hardware/model.
- Throughput scales by adding independent generation workers.

The system can be highly optimized and scalable, but there is no universal
"maximum optimization." Latency, completeness, hardware cost, and verification
strength trade against one another. The correct goal is a measured service
level with non-negotiable legal quality and safety gates.

## 11. Immediate acceptance checklist

- [x] Preserve Fast deterministic retrieval.
- [x] Keep cross-encoder disabled.
- [x] Preserve current-law ranking penalty.
- [x] Preserve claim verification and no-unsupported-publication rule.
- [x] Add endpoint timing buckets.
- [x] Collect fresh warm and cold Fast API timing samples from the running stack.
- [x] Implement and test the first right-to-implementation bridges.
- [ ] Re-run 61-question retrieval evaluation.
- [x] Re-run 8-question governing-provision evaluation: 8/8 reached.
- [x] Run focused backend regression suite: 70/70 passed.
- [x] Rebuild backend image and verify PostgreSQL, Qdrant, MinIO and Ollama readiness.
- [ ] Run controlled Deep A/B experiments.
- [ ] Run full answer evaluation before accepting model/prompt changes.
- [ ] Validate and stage the downloaded Phase A corpus.
- [ ] Promote new corpus only after all gates pass.
