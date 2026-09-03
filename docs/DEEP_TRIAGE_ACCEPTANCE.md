# Deep Review Phase 0 triage — acceptance record

Measured: **29 August 2026 IST**

## Status

| Gate | Accepted value / qualification |
| --- | --- |
| Five deliberate reproductions | **Accepted for latency triage:** 5 requested, 5 workflows returned, 0 errors; all 5 reasoning drafts reached the 900-token limit, so this is not an output-quality acceptance |
| Historical `>180,000 ms` condition | **Reproduced:** run 1 took `208447.480459 ms`; 1 of 5 runs exceeded the threshold |
| Per-node timing evidence | **Accepted:** all 5 runs contain role context, query understanding, retrieval, reasoning, verification, response generation and workflow-total timings |
| Input-size evidence | **Accepted:** reranker chunk/byte counts and actual Ollama `prompt_eval_count`/context-window values are present for every applicable stage |
| Reasoning truncation correction | **Accepted for the reproduced scenario:** reasoning ceiling raised from 900 to 1,800 tokens; 2 of 2 confirmation runs returned `done_reason=stop` at 1,345 tokens |
| Submission definition sign-off | **Accepted:** the user explicitly confirmed teammate/guide sign-off on 29 August 2026 |
| Phase 0 | **Closed:** latency/input evidence, truncation correction and human agreement gates are met |

Phase 1 has not started. No new product feature was added during this triage.

## Reproduction contract

The same synthetic citizen query was run sequentially five times through the
real LangGraph Deep workflow, BGE-M3 query embedder, Qdrant hybrid retrieval,
BGE reranker and local Ollama model. Sequential execution prevents concurrent
requests from competing for the one local model during this baseline.

Model: `qwen3-14b-16k:latest`, 11 GB, 100% GPU according to `ollama ps`, with a
configured `16384`-token context window. Host: arm64 macOS, Python 3.12.13, 18
logical CPUs. The query asked for a CrPC section 154 versus BNSS section 173
comparison, commencement/transition, procedural differences, refusal
escalation and explicit current-law uncertainty using only retrieved sources.

The initial accidental fetch into the default Hugging Face cache was cancelled
before this five-run set. The measured set used the project's existing shared
model cache. Run 1 still includes normal in-process cold loading of BGE-M3;
runs 2–5 show query-embedding cache hits. No interrupted attempt is counted as
one of the five records.

Raw machine-readable evidence:
[`evidence/deep-triage-raw.json`](evidence/deep-triage-raw.json).
The two post-fix confirmation runs are preserved separately in
[`evidence/deep-triage-reasoning-limit-rerun.json`](evidence/deep-triage-reasoning-limit-rerun.json).

## End-to-end results

| Run | Wall time (ms) | Over 180,000 ms | Completed | Retry count | Citations |
| ---: | ---: | --- | --- | ---: | ---: |
| 1 | 208447.480459 | yes | yes | 0 | 2 |
| 2 | 148403.372333 | no | yes | 0 | 2 |
| 3 | 117282.222542 | no | yes | 0 | 2 |
| 4 | 120747.657583 | no | yes | 0 | 2 |
| 5 | 115913.984083 | no | yes | 0 | 2 |

Observed minimum: `115913.984083 ms`; maximum: `208447.480459 ms`; arithmetic
mean: `142158.943400 ms`; median: `120747.657583 ms`. These are complete-response
times, not time-to-first-token measurements.

## Per-node latency breakdown

| Node | Run 1 ms | Run 2 ms | Run 3 ms | Run 4 ms | Run 5 ms | Median ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Role context | 0.069042 | 0.542917 | 0.103958 | 0.085959 | 0.349708 | 0.103958 |
| Query understanding | 12601.948333 | 13151.013458 | 11131.838333 | 10970.309834 | 10833.788791 | 11131.838333 |
| Retrieval | 19796.162875 | 12828.382584 | 7498.624125 | 10868.047042 | 9116.612833 | 10868.047042 |
| Reasoning | 124607.025000 | 81976.756209 | 81947.601084 | 82649.229792 | 79963.989667 | 81976.756209 |
| Verification | 51385.312000 | 40397.144708 | 16668.239583 | 16223.797833 | 15972.293333 | 16668.239583 |
| Response generation | 1.237917 | 1.074500 | 0.918791 | 1.555792 | 0.858125 | 1.074500 |
| Workflow total | 208446.806083 | 148402.127541 | 117281.837250 | 120747.299667 | 115913.521500 | 120747.299667 |

The small difference between harness wall time and `workflow_total` is harness
bookkeeping around the graph invocation.

## Retrieval and reranker input

The reranker received the same `20` fused candidate chunks on every run, with
`5` results retained. The raw document side contained `80845` characters and
`80995` UTF-8 bytes. Its query side contained `437` characters/bytes and was
repeated for every pair, so query plus document text totalled `89585` characters
and `89735` bytes before tokenizer special tokens or truncation. This is not the
total dense+sparse prefetch workload. The configured maximum was `8192` tokens
independently for each query/document pair; it was not one shared reranker
context and no tokenizer-derived reranker input count was observed.

| Run | Embedding cache | Embedding ms | Qdrant ms | Reranking ms | Retrieval service total ms |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | miss | 11928.25 | 224.43 | 7637.24 | 19791.16 |
| 2 | hit | 4.24 | 242.73 | 12575.35 | 12822.62 |
| 3 | hit | 2.98 | 149.38 | 7341.79 | 7494.58 |
| 4 | hit | 3.68 | 149.10 | 10714.38 | 10867.30 |
| 5 | hit | 3.70 | 138.80 | 8972.55 | 9115.19 |

## Ollama input and generation evidence

`prompt_eval_count` and `response_eval_count` below are values returned by
Ollama, not whitespace estimates. Prompt-context utilization is
`prompt_eval_count / 16384`.

| Stage | Run(s) | Prompt tokens | Prompt-context utilization | Response tokens | Stop reason |
| --- | --- | ---: | ---: | ---: | --- |
| Query understanding | 1–5 | 296 | 0.01806640625 | 141 | `stop` |
| Reasoning | 1–5 | 6496 | 0.396484375 | 900 | `length` |
| Verification | 1 | 7977 | 0.48687744140625 | 125 | `stop` |
| Verification | 2–5 | 7972 | 0.486572265625 | 125 | `stop` |

The reasoning prompt contained `25223` characters (`25271` UTF-8 bytes) and
five retrieved chunks. The verification prompt contained `33234` characters
(`33302` UTF-8 bytes) in run 1 and included the draft plus evidence for six
claim markers. The exact Ollama count shows that neither prompt filled the
16,384-token context window, although verification consumed almost half of it.

| Run | Sum of measured LLM-call wall time (ms) | Share of run wall time |
| ---: | ---: | ---: |
| 1 | 188545.893208 | 90.4524692708317539012139890554% |
| 2 | 135492.268959 | 91.2999932743920551861007957624% |
| 3 | 109716.148792 | 93.5488315398435519528679704034% |
| 4 | 109811.694084 | 90.9431257567188875874658879427% |
| 5 | 106748.237625 | 92.0926309879601034850058420108% |

## Evidence-backed diagnosis

### Correctness finding: reasoning output truncation — corrected for this scenario

**Open defect at the time of the five-run baseline:** all five reasoning calls
returned exactly `900` response tokens with `done_reason=length`. The verifier
therefore evaluated truncated drafts. This is a correctness defect, not merely
a latency observation: a cutoff can omit a qualification, adverse authority,
current-law warning or concluding source marker even when the preceding text is
grounded. The five-run baseline must not be treated as answer-completeness or
accuracy acceptance.

The reasoning-stage ceiling was raised from `900` to `1800` without changing
the query-understanding or verification ceilings. The same synthetic scenario
was then repeated twice:

| Confirmation run | Reasoning ceiling | Reasoning response tokens | Stop reason | Reasoning ms | Workflow wall ms |
| ---: | ---: | ---: | --- | ---: | ---: |
| 1 | 1800 | 1345 | `stop` | 162644.442583 | 295737.854958 |
| 2 | 1800 | 1345 | `stop` | 143489.762959 | 268594.616917 |

Both confirmation runs completed without an error or verification retry. This
closes the observed 900-token truncation defect for the reproduced scenario; it
does not constitute broader legal-answer accuracy acceptance. The larger draft
also increased verification input to `12893` and `13124` Ollama prompt tokens
respectively, compared with `7972–7977` in the baseline. Verification remained
inside the `16384` context window and returned `done_reason=stop` in both runs.

The correctness correction worsened synchronous latency: both confirmations
exceeded the historical 180-second threshold. Phase 1 must address responsiveness
without reintroducing output truncation.

### Latency finding

Ollama inference is the dominant bottleneck in every reproduction: measured LLM
calls account for more than 90% of each wall time. Reasoning is the largest node
in all five runs and always reaches its `900`-token generation limit with
`done_reason=length`. The workflows returned, but the reasoning drafts were
token-limit truncated; this evidence diagnoses latency and does not accept
answer completeness or accuracy. Slow Deep execution is not explained solely
by an oversized prompt: the reasoning input uses 39.6484375% of the model context,
but generation still emits the full configured output allowance at roughly
9.443788754029953 to 11.90482363347704 response tokens per second.

Input size also matters. On run 1, reasoning prompt evaluation took
`29064.313 ms` and verification prompt evaluation took `37519.257 ms` for
`6496` and `7977` prompt tokens respectively. Repeated identical runs benefited
from Ollama-side prompt reuse: by run 3, those prompt-evaluation durations were
`59.898 ms` and `100.449 ms`. This explains much of the large cold/warm spread,
but warm runs still took between `115913.984083 ms` and `148403.372333 ms`.

Retrieval is secondary, not free. It ranged from `7498.624125 ms` to
`19796.162875 ms`; the first-run embedding miss cost `11928.25 ms`, while warm
embedding hits took `2.98–4.24 ms`. Reranking the same 20 chunks ranged from
`7341.79 ms` to `12575.35 ms`.

No verification correction retry occurred in this scenario, so retries did not
cause these five slow results. Retry-indexed telemetry is covered by automated
tests that force two correction retries. Failure-path tests separately verify
that a failed node and failed workflow total are emitted without logging an
Ollama response body.

These are five repetitions of one deliberately difficult synthetic query, not
a production latency distribution. Run 1 includes an embedding-cache miss;
runs 2–5 include application embedding-cache hits and repeated-prompt reuse.
Mean and median are descriptive only for this reproduction set.

## Verification gates run for this change

| Gate | Observed result |
| --- | --- |
| Focused reasoning-limit/telemetry/agent/chat suite | 13 passed in 1.96 s |
| Complete backend regression for the reasoning-limit diff | 120 passed in 14.77 s |
| Python syntax compilation | passed |
| `git diff --check` | passed |
| Live Deep reproductions | 5 completed, 0 errors |
| Post-fix natural-stop confirmations | 2 completed, 0 errors; reasoning `done_reason=stop` in both |

The test process required host-specific endpoint overrides because `.env` uses
Docker DNS names (`minio`, `qdrant`, and `host.docker.internal`). The first
unqualified full-suite attempt produced 116 passes and two MinIO hostname
failures; it is not reported as a passing gate. With equivalent host endpoints,
the complete suite passed. The sole warning in both passing test runs is the
existing Passlib import of Python's deprecated `crypt` module.

An intermediate post-review full-suite run produced 119 passes and one grammar-
fallback compatibility failure. That compatibility issue was corrected and is
not counted as a passing gate; the subsequent complete run is the 120-pass
result above.

## Agreed submission definition

Proposed submission definition, copied from the authoritative completion plan:

> Fast Research, FIR drafting, defence analysis, and Document Analyzer all work
> end-to-end for all four roles, Deep mode never hangs past 60s, and there's a
> written accuracy record against a hand-graded eval set.

The user explicitly confirmed the required teammate/guide sign-off on 29 August
2026. Phase 0 is therefore closed. The paragraph remains the controlling scope
definition for the later completion phases.
