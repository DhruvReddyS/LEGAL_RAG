# Fast and Deep response latency: what was measured, what changed, what did not

*8 October 2026. Corpus `global_legal_corpus_v4`, 49,684 points. Backend
running natively with BGE-M3 on MPS; Postgres, Qdrant and MinIO in Docker;
Ollama native with `qwen3-14b-16k` resident at 11.7 GB.*

Written for someone deciding whether to trust these numbers. The headline is
not a speed-up. It is that **Deep's latency is 97% language model and 0.1
seconds of everything this repository controls**, and that one change made in
pursuit of speed cost a fifth of the published citations before measurement
caught it.

---

## 1. Environment and protocol

| | |
|---|---|
| Host | MacBook Pro, Apple M5 Pro, 18 cores, 24 GB unified memory, macOS 27.0 |
| Reasoning model | `qwen3-14b-16k` (14.8B, Q4_K_M), `num_ctx` 16384, `temperature` 0.0, one slot (`-np 1`) |
| Embedder / reranker | BAAI/bge-m3 on MPS; cross-encoder reranking off (`cross_encoder_reranking_enabled=false`) |
| Vector store | Qdrant v1.18.2, `global_legal_corpus_v4`, 49,684 points, status green |
| Query set | `latency-v1`, 7 questions, frozen (see §2) |
| Repeats | 3 per question per mode, one discarded warm-up per mode |
| Harness | `scripts/latency_benchmark.py` |
| Comparison | `scripts/latency_compare.py` |
| Gate | `scripts/check_latency_gate.py` |

Fast is measured synchronously on `POST /chat/query`. Deep is measured through
the durable job path it actually uses -- `POST /jobs/deep-review` plus its
event stream -- because synchronous Deep is disabled in configuration.

Every run records the host's load average, swap-out rate, resident Ollama
models, Qdrant collection and point count, git commit and the job-queue depth
at start. A run refuses to begin if the host is paging, if the normalised load
is above 0.75, if a corpus task is running, or if any job is queued.

### Measurement validity

Four runs were taken. Two were discarded, and both failures are recorded in
[`LATENCY_COORDINATION.md`](LATENCY_COORDINATION.md) rather than deleted,
because a benchmark whose failures are not written down cannot be audited.

| Run | Outcome |
|---|---|
| W2 | **void.** The Fast phase auto-escalates low-confidence answers into Deep jobs. The Deep measurement sat six minutes behind three of them and would have recorded the queue as pipeline latency. |
| W3 | **void.** A three-repeat Deep pass outlives the 30-minute access token. It died on the final poll of the last query, losing 38 minutes of measurement. |
| W4 | the baseline in this report. |
| W5-W7 | the change passes in §4. |

A third defect was in the metric rather than the run: `stage_breakdown` read
key names the pipeline does not write, so the first baseline recorded prompt
tokens, prefill and LLM duration as **zero** -- and a zero there reads as
"free" rather than "not measured". The job results are persisted, so
`scripts/latency_repair_llm_accounting.py` re-derived them from the database
rather than spending another 38 minutes; the repair is recorded in the report
file it rewrote.

All three are now guarded, and the harness has 14 tests of its own arithmetic.

### Two properties of this host that invalidate naive comparison

**It thermally throttles.** The same question, the same input, three repeats
inside one 25-minute pass:

| | repeat 0 | repeat 1 | repeat 2 |
|---|---:|---:|---:|
| q01 | 50.7 s | 73.0 s | 72.0 s |
| q04 | 113.9 s | 142.5 s | 150.5 s |

Across runs it is larger still. The same reasoning prompt producing the same
597 output tokens took **42.5 s** on a laptop that had been hot for an hour and
**26.4 s** on a cool one: 14.0 against 22.6 tokens per second. Any Deep timing
quoted without the decode rate beside it is unreliable, which is why
`latency_compare.py` now prints the decode rate *before* the latency table and
warns when the host moved by more than 10%.

**It is not reproducible.** At temperature 0, q02 published a 312-word answer
at verification 0.75 on one repeat and abstained at 0.43 on the next two, same
input. Metal floating-point accumulation varies with batch splits, one token
flips, and the draft diverges. Quality must be read as a rate over repeats,
never as a per-query difference.

---

## 2. The query set

Chosen to exercise the behaviours the acceptance criteria protect, not to
flatter the timings. Frozen as `latency-v1`; a before/after comparison across
a different version is refused rather than averaged.

| id | role | what it tests |
|---|---|---|
| q01 | citizen | arrest without warrant -- a provision the corpus holds |
| q02 | citizen | rights of an arrested person |
| q03 | citizen | FIR registration -- reached only by following citations |
| q04 | citizen | Article 14 -- the broadest question in the set |
| q05 | citizen | lay-worded consumer complaint, no shared vocabulary with the statute |
| q06 | police | chain of custody -- puts role profiles on the measured path |
| q07 | citizen | contract law, which the corpus does not hold -- **abstention expected** |

q05 and q07 are in the set deliberately. An optimisation that abstains more
often is faster and worse, and without a question the system should refuse,
that cannot be seen.

---

## 3. Baseline

### End to end

| | Fast | Deep |
|---|---:|---:|
| p50 | **0.09 s** | **64.95 s** |
| p95 | **0.18 s** | **142.47 s** |
| min / max | 0.03 / 0.21 s | 30.5 / 150.5 s |
| time to first useful output, p50 | 0.09 s | **64.66 s** |
| configured budget | 5 s | 300 s |
| runs | 21 | 21 |

Fast is 28 times inside its budget and needs nothing. A brand-new question
costs 0.11-0.21 s, of which 0.06-0.13 s is the BGE-M3 query embedding and
0.013-0.048 s is Qdrant; a repeated question costs 0.03-0.05 s because the
query-embedding cache answers it.

### Where Deep's 65 seconds go

| Stage | p50 | Share |
|---|---:|---:|
| reasoning (LLM) | 52.40 s | 80.7% |
| verification (LLM) | 10.10 s | 15.6% |
| retrieval | 0.086 s | 0.1% |
| retrieval enrichment | 0.016 s | 0.0% |
| response generation | 0.002 s | 0.0% |
| query understanding | 0.0002 s | 0.0% |
| role context | 0.00006 s | 0.0% |

Split by what the model is doing:

| | p50 |
|---|---:|
| token decode | 45.95 s (71%) |
| prompt prefill | 16.58 s (26%) |
| generation queue wait | 0.00 s |
| model load | 0.016 s |
| decode rate | 14.4 tokens/second |
| output tokens per query | 675 |
| prompt tokens per query | 7,965 |
| model calls per query | 2.86 |

Per call:

| call | n | prompt tok | output tok | prefill | decode |
|---|---:|---:|---:|---:|---:|
| reasoning, first pass | 21 | 4,053 | 597 | 9.5 s | 42.5 s |
| reasoning, retry pass | 3 | 4,067 | 677 | 11.7 s | 48.5 s |
| verification, first pass | 30 | 2,012 | 35 | 2.0 s | 1.6 s |
| verification, retry pass | 3 | 3,039 | 52 | 7.4 s | 2.7 s |

**This is the finding that governs everything else.** The orchestration --
retrieval, citation following, enrichment, diversity selection, citation
construction, currency and repeal labelling, persistence -- is 0.1 seconds of
a 65-second run. There is no idle wait, no queue, no cold start and no
redundant round trip left to remove. Deep latency is, to within a rounding
error, `prompt_tokens / 428 + output_tokens / 14.4` seconds.

Two consequences:

1. A faster Deep means fewer output tokens, faster tokens, or not making the
   reader wait for all of them. Fewer tokens means a shorter answer, which is
   out of scope. Faster tokens means a different model, and **the decision has
   been taken not to compromise the local model's quality**, so the 14B stays
   and ~45 s of decode for a 675-token verified answer is the floor on this
   hardware.
2. A latency *gate* on Deep end-to-end would be a thermometer. §5 explains
   what is gated instead.

### Where the p95 goes

The 142 s p95 is the retry pass. Three of 21 runs retried, all of them q04,
each adding a second reasoning call: 113.9 s, 142.5 s, 150.5 s against a
52-76 s median elsewhere. The retry is productive there -- it is where two of
q04's six citations come from -- so it is not waste to remove.

---

## 4. What changed, and what each change is and is not responsible for

Four changes shipped. One was reverted after measurement. Attribution is
stated per change, because the raw before/after latency delta is **not**
attributable: the later runs decoded at 22.9 tokens/second against the
baseline's 14.4, a 58% faster host, and the retry stopped firing.

### 4.1 Deep publishes its sources before it has an answer — kept

Deep's first source-backed event was a citation, written only after
verification finished. Time to first useful output was therefore identical to
end to end.

Retrieval completes at **0.57 s**. The authorities it located now publish
then, as their own job event and as a `located_sources` field on the job
record: eight sources with act, section, pages, currency status and repeal
labels. Every entry carries `verification_status: "unverified"` and
`is_final_answer: false`, stated per entry rather than in the envelope so a
client that iterates the list cannot drop the disclaimer. Global corpus only:
a case-scoped Deep run also retrieves the owner's own case material, and
interim progress is not the place to widen where that text appears.

| | before | after |
|---|---:|---:|
| time to first useful output, p50 | 64.66 s | **0.57 s** |
| time to first useful output, p95 | 142.46 s | 6.16 s |
| time to first *final* output, p50 | 64.66 s | unchanged |

**Attributable.** Retrieval's completion time is measured directly and cannot
move with decode throughput. The final verification and citation gates are
untouched; nothing unverified is presented as an answer.

### 4.2 Deep's term-frequency lookup overlaps its search — kept

The distinctive-term frequencies are Qdrant counts over the user's own
question, with no dependence on what the search returns. The Fast lane has
always run that lookup alongside its search; Deep waited for the search to
finish first. Now dispatched before it, and awaited after.

Worth 0.016 s at p50 and 0.044 s at p95 -- immaterial to a 65-second run, kept
because it is free, carries no behaviour change, and removes a serialisation
that would grow if the lookup ever did.

### 4.3 The query embedder warms until it stops getting faster — kept

Production warmed the embedder with one encode. Measured on this host with a
freshly loaded BGE-M3: a short query encodes in 286 ms at the median, 73 ms
after another seven calls, and 33 ms after seven more. The curve is not about
the query -- 6-token and 96-token inputs converge together, and in one pass a
20-token query cost 70 ms while a 32-token one cost 614 ms -- so it is kernel
compilation and allocator warming amortised over the first calls.

One encode therefore left the next dozen real queries paying it. Observed in
the first Fast pass: the first query after a restart spent **682 ms** in the
embedder, against 0 ms once cached. Warm-up now encodes distinct strings of
varying length until two consecutive calls are flat, bounded at 24 encodes,
and logs how many it needed.

Bounded by convergence rather than a fixed count because the curve belongs to
the host: a CPU-only deployment and an accelerated one do not flatten after
the same number of calls. On an already-warm host it stops after four encodes
and costs ~100 ms of boot. Readiness gates on it, so no request waits.

### 4.4 The verifier verdict-count change — **reverted**, and this is the important one

The verifier returned fewer verdicts than it was sent in 9 of 21 baseline
runs. Each occurrence cost a second request (mean 2.07 s) and, worse, any
claim still unjudged afterwards was recorded as **refuted** -- suppressing
verified law the verifier had never rejected.

Two things were changed together: a sampling grammar pinning the verdict array
to `minItems == maxItems == claim_count`, and a sentence in the prompt stating
that count.

**Isolating them showed the grammar was doing nothing.** A 21-run pass with
the sentence and no grammar produced the identical result:

| | baseline | sentence + grammar | sentence only |
|---|---:|---:|---:|
| runs needing a second verification request | 9 / 21 | 0 / 21 | 0 / 21 |
| model calls per query | 2.857 | 2.143 | 2.143 |
| unadjudicated claims per query | 0.095 | 0.0 | 0.0 |
| citations per query | **3.143** | **2.429** | **2.429** |
| answers graded insufficient but published | 9.5% | 28.6% | 28.6% |
| runs that retried | 3 / 21 | 0 / 21 | 0 / 21 |

The sentence was the entire effect -- and the entire cost. A targeted re-run of
the two questions that moved, with the sentence removed and nothing else
changed:

| | baseline | with the sentence | sentence reverted |
|---|---|---|---|
| q02 | 4 cites, 312 w, moderate | 1 cite, 212 w, insufficient | **5 cites, 350 w, strong** |
| q04 | 6 cites, 344 w, moderate | 4 cites, 227 w, insufficient | **6 cites, 344 w, moderate** |

The mechanism is now clear. A claim the verifier left unjudged was excluded
from the support denominator and never published. A verdict forced on that
same claim is often an explicit "no" that *counts against* the score -- enough
to push a weak first pass over the publication bar, which stops the retry
firing, and the retry was where two of q04's six citations came from.

Both the sentence and the grammar now sit behind
`verification_exact_verdict_grammar_enabled`, **off by default**. The default
is the behaviour that produces more citations. Turning either on needs a run
of its own against the golden set.

This is the headline result of the work: a change that looked like a pure win
on call counts and unadjudicated claims was costing a fifth of the published
citations, and only a before/after comparison that recorded citation counts
beside the timings could see it.

---

## 5. Preventing recurrence

Four of the problems above were invisible to 1,149 passing tests. The
following close that gap.

### A gate on what this repository controls

`scripts/check_latency_gate.py`, in the style of the three existing CI gates.
It deliberately does **not** gate Deep end-to-end, because that number is
output tokens divided by the host's decode rate. It gates:

| gated | why |
|---|---|
| `fast_p95_ms` | Fast runs no model, so its end-to-end number is the code's own |
| `deep_non_model_overhead_p95_ms` | every Deep stage that is not reasoning or verification -- where a serialisation or an N+1 query lands, and where four seconds is invisible beside a 52-second model call |
| `deep_first_useful_output_p95_ms` | a change that moved the source event back behind verification would restore the 65-second wait with no other number moving |
| `citations_per_query` | speed must not be bought with evidence |
| `abstention_rate` | refusing more often is not an optimisation |
| `unsupported_claims_per_query` | checking less is not an optimisation |

Decode rate and end-to-end are recorded as context and never gated. A run
carrying validity warnings can neither set nor pass the gate. A contract
recorded against a different query-set version is refused rather than
compared.

### Honesty about the host, in the output

`latency_compare.py` prints the decode rate and token counts above the latency
table, and when the host moved by more than 10% it says in bold that the
end-to-end deltas are not attributable to the code. A reader cannot reach a
conclusion from the timings before reaching the explanation.

### Separating perceived from real

Time to first *useful* output and time to first *final* output are recorded
separately, so progressive streaming can never be presented as a faster
answer.

### Abstention measured as what it is

The harness read `evidence_strength == "insufficient"` as a refusal. Deep
publishes a 247-word answer with four citations while grading it insufficient,
so that reported 29% abstention on a set where the pipeline refuses one
question in seven. It now tests the refusal text, and reports "published but
graded insufficient" as a separate metric -- the band an optimisation could
quietly push answers into.

### Comparisons recompute, never read a summary

`latency_compare.py` derives every metric from both runs' stored records, so a
definition corrected after the baseline was taken applies to the baseline too.
That is what made a baseline recorded under the wrong abstention rule usable
instead of discarded. Raw `pipeline_metrics` are stored verbatim in every
report, so the next accounting mistake is a re-analysis rather than another 38
minutes of machine time.

---

## 6. Two defects found on the way that were not latency at all

### Chat history could show the answer above the question

`chat_messages.created_at` defaults to `now()`, which in PostgreSQL is the
*transaction* timestamp. A chat request writes the question and the answer in
one transaction, so both rows carry a byte-identical value and ordering by it
is left to the planner. Measured on the development database: **1,225 of 2,912
stored messages share a timestamp with a sibling in the same session.**

`test_chat_persistence_and_session_ownership` had been failing about one run in
three with `['assistant', 'user']` and was being read as a flaky test rather
than as the product bug it was reporting. The session-list query had already
hit the same collision and worked around it in place.

Fixed with a monotonic `sequence` column (migration `c7e2a9b41d08`, verified
down and up against the 2,912 stored rows), so insert order is a fact of the
row instead of a rule each query must remember. The workaround is gone. The
previously flaky test now passes five times out of five.

### No citation could be opened

The canonical manifest records an official URL for **1,026 of its 1,036
documents**. None of them ever reached a reader. `LegalChunk` had no
`source_url` field, so the chunker dropped it, so `legal_chunk_payload` never
wrote the key -- while the Fast lane, Deep's response generation, the interim
source list and the defence strategy agent all read
`payload.get("source_url")` and all got `None`. Measured against the live
index: **0 of 200 sampled points carried it.**

Every citation in the product named a provision and gave the reader no way to
go and read it. The plumbing is fixed, so anything ingested from now on carries
it, and a test asserts the key name on both sides of the contract.

`scripts/backfill_source_urls.py` gives the already-indexed points the same
field: a payload-only update keyed on `document_id`, no vectors, no
re-embedding. The join key was verified present on 300 of 300 sampled points
and on all 1,036 manifest documents. **It has not been run.** It mutates a
Qdrant collection and another agent is collecting; it is queued for the
finalisation phase.

---

## 6a. The one valid before/after comparison

Every earlier pass ran on a host whose decode rate differed from the
baseline's, so none of them could attribute a latency delta. The final pass
decoded at **14.5 tokens/second against the baseline's 14.4** -- the same
machine, in the same state -- so this is the comparison that counts.

| | baseline | final | attributable |
|---|---:|---:|---|
| Fast p50 | 0.09 s | **0.03 s** | yes -- the embedder warm-up |
| Fast p95 | 0.18 s | **0.14 s** | yes |
| Fast citations per query | 3.29 | 3.29 | unchanged |
| Deep time to first useful output, p50 | 64.66 s | **0.56 s** | yes -- sources publish at retrieval |
| Deep p50 | 64.95 s | 72.16 s | **no** -- see below |
| Deep p95 | 142.47 s | 140.25 s | unchanged |
| Deep citations per query | 3.14 | **3.19** | held |
| Deep abstentions | 5 / 21 | **3 / 21** | improved |
| Deep answers graded strong | 3 | 4 | improved |
| Deep retries | 3 / 21 | 3 / 21 | unchanged |
| Deep output tokens, p50 | 675 | 675 | unchanged |

Four of the seven questions returned **byte-identical** answers at
near-identical timings. q02 improved: two of its three repeats had abstained
in the baseline and none did here, and one produced a 350-word answer graded
strong where the baseline's best was 312 words graded moderate.

The Deep p50 moving from 65.0 s to 72.2 s is **not** a code regression, and the
per-stage accounting says so. It is q05 (+21 s) and q03 (+4 s), and in both
cases the work is identical:

| | baseline | final |
|---|---|---|
| q05 output tokens / model calls / decode rate | 745 / 3 / 14.2 | 745 / 3 / 14.1 |
| q05 reasoning, verification | 48.1 s, 6.1 s | 57.9 s, 13.7 s |
| q03 output tokens / decode rate | 716 / 13.8 | 722 / 14.1 |

The same token count at the same tokens-per-second took longer inside the
stage. That is this host's thermal behaviour within a 25-minute pass -- the
same effect that took q01 from 50.7 s to 73.0 s across three repeats of one
question in a single baseline run. It is the reason the gate does not gate
Deep end-to-end.

### The gate, verified in both directions

The contract is recorded from this run. Run against itself it passes. Run
against the baseline it fails, on exactly the two properties the work
defended:

```
deep_non_model_overhead_p95_ms is 979 ms against a limit of 488 ms
deep_first_useful_output_p95_ms is 142,458 ms against a limit of 15,341 ms
```

## 7. Remaining bottlenecks

| | |
|---|---|
| **Deep decode, 46 s at p50** | 675 output tokens at 14.4 tokens/second. Fixable only by fewer tokens (a shorter answer), a faster model (declined -- local quality is not to be compromised), or better hardware. Not an engineering defect. |
| **Deep prefill, 17 s at p50** | 7,965 prompt tokens at ~428/second, of which ~3,600 is the evidence block. Cannot shrink without shrinking the evidence. The verification call re-sends premises reasoning already sent; making them a shared literal prefix so llama.cpp reuses the slot's KV cache would save ~2 s, and is a prompt-semantics change on the component where §4.4 just showed what an unmeasured prompt change costs. Not attempted. |
| **The retry pass** | 3 of 21 runs, +60 s each, and the entire p95. Productive where it fires. Whether it fires is decided by non-deterministic verdicts. |
| **Query understanding** | fires on 3 of 21 runs (a first-turn question containing a pronoun) and costs 6.5 s when it does. The code records a deliberate, tested decision that skipping it costs retrieval quality. Overturning that needs a golden-set retrieval measurement, not an opinion. Defined, not done. |
| **Generation concurrency is 1** | `-np 1` on one Ollama slot, and the job worker runs Deep jobs serially. Queue wait measured 0.00 s because the benchmark is single-user. With real users, the second concurrent Deep request waits for the first: two users means a 95-second p50. This is the scalability ceiling for the v1 release and it is unmeasured under load. |
| **Fast auto-escalation is invisible** | a low-confidence Fast answer enqueues a Deep job; three fired during each Fast benchmark phase. Nothing alerts on queue depth, and each escalation delays the next real Deep request by 30-150 s. |

## 8. Files changed

**Measured query path**
`backend/app/agents/orchestrator.py`, `backend/app/agents/located_sources.py` (new),
`backend/app/agents/retrieval_agent.py`, `backend/app/agents/verification_agent.py`,
`backend/app/services/retrieval.py`, `backend/app/services/job_worker.py`,
`backend/app/routers/jobs.py`, `backend/app/schemas/jobs.py`,
`backend/app/core/config.py`

**Citations and conversation order**
`backend/app/ingestion/chunker.py`, `backend/app/ingestion/qdrant_writer.py`,
`backend/app/ingestion/restore_chunks.py`, `backend/app/models/chat.py`,
`backend/app/routers/chat.py`,
`backend/alembic/versions/c7e2a9b41d08_add_chat_message_sequence.py` (new)

**Measurement and gates**
`scripts/latency_benchmark.py`, `scripts/latency_compare.py` (new),
`scripts/check_latency_gate.py` (new),
`scripts/latency_repair_llm_accounting.py` (new),
`scripts/backfill_source_urls.py` (new, not run)

**Tests** (+24, suite 1,125 -> 1,149, no failures)
`test_latency_benchmark_harness.py`, `test_latency_comparison.py`,
`test_latency_gate.py`, `test_located_sources_progress.py`,
`test_verdict_schema_is_exact_length.py`, `test_embedder_warmup_converges.py`,
`test_chat_message_order_is_stable.py`, `test_citations_carry_their_source.py`,
and the three fakes updated to accept a `VerificationBatch` subclass.

No corpus artefact, source manifest, candidate import, promotion, ingestion or
Qdrant collection was mutated by this work.

## 9. Evidence files

| file | what it is |
|---|---|
| `both-baseline.json` | the baseline, 21 Fast and 21 Deep runs, LLM accounting repaired from the database |
| `both-after.json` | sentence and grammar on |
| `both-shipped.json` | sentence on, grammar off -- the pass that isolated them |
| `both-final.json` | the shipped configuration |
| `comparison.md` | generated by `latency_compare.py` |
| `latency-contract.json` | the gate's recorded floor |
| `fast-baseline.json` | the first Fast pass, taken ~1 minute after a restart, which is where the 682 ms cold embedding was observed |
| `LATENCY_COORDINATION.md` | the handshake with the agent collecting the corpus, and the window log including the void windows |
