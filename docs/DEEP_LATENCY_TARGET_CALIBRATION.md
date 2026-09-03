# Deep Review Phase 1 latency-target calibration

Measured: **29 August 2026 IST**

## Decision status

Phase 0 is closed. Phase 1 implementation has **not** started. This calibration
exists to replace the pre-measurement 60-second assumption with a target that
separates user-visible responsiveness, queue delay and correctness-safe model
service time. The proposed target below requires explicit user approval before
durable-job, SSE or concurrency work begins.

## Controlled comparison

The same synthetic citizen query, model, `16384` context window, BGE retrieval,
reranker and LangGraph workflow were used throughout. Runs were sequential on
the local `qwen3-14b-16k:latest` host. The reasoning output ceiling was the only
intentional variant. Each new ceiling has two repetitions; this is enough to
confirm the observed truncation behavior, but not enough to claim p50/p95/p99.

Prior evidence was not overwritten:

- [`evidence/deep-triage-raw.json`](evidence/deep-triage-raw.json): original
  five-run 900-token baseline.
- [`evidence/deep-triage-reasoning-limit-rerun.json`](evidence/deep-triage-reasoning-limit-rerun.json):
  two correctness-safe 1,800-token confirmations.
- [`evidence/deep-triage-reasoning-1100.json`](evidence/deep-triage-reasoning-1100.json):
  two 1,100-token calibration runs.
- [`evidence/deep-triage-reasoning-1300.json`](evidence/deep-triage-reasoning-1300.json):
  two 1,300-token calibration runs.

Evidence SHA-256 values at report completion:

| Evidence file | SHA-256 |
| --- | --- |
| `deep-triage-raw.json` | `66ef6b9ae6d88925193a20637b1f204635a41fd22ff8fabf05a235bf36bfb753` |
| `deep-triage-reasoning-limit-rerun.json` | `3acf4085a11c20ad3faae4df0b987ba078fa17fc8c09fb4ad6c4588811a67c94` |
| `deep-triage-reasoning-1100.json` | `eec7cbd573752f4a226d598682e07ef2c5fdf62f26e79fcd10301ee94e2177cf` |
| `deep-triage-reasoning-1300.json` | `db1fe41de789e21f2f38a0925ce22851e34e4322225cf0e906be3d9b7824da45` |

## Exact new observations

| Ceiling | Run | Reasoning tokens | Reasoning stop | Reasoning ms | Verification prompt tokens | Verification ms | Workflow wall ms |
| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 1100 | 1 | 1100 | `length` | 122875.371583 | 9295 | 54619.546916 | 217078.454542 |
| 1100 | 2 | 1100 | `length` | 99679.119333 | 9288 | 49397.349917 | 173947.176209 |
| 1300 | 1 | 1300 | `length` | 111662.103625 | 11793 | 37968.736916 | 178647.584750 |
| 1300 | 2 | 1300 | `length` | 112739.232834 | 11793 | 25486.468167 | 161740.491334 |
| 1800 | 1 | 1345 | `stop` | 162644.442583 | 12893 | 94373.267542 | 295737.854958 |
| 1800 | 2 | 1345 | `stop` | 143489.762959 | 13124 | 97151.328000 | 268594.616917 |

Descriptive arithmetic means for these two-run samples, without converting
them into percentile claims:

| Ceiling | Mean wall ms | Natural-stop rate | Correctness qualification |
| ---: | ---: | ---: | --- |
| 1100 | 195512.8153755 | 0/2 | rejected: both drafts truncated |
| 1300 | 170194.038042 | 0/2 | rejected: both drafts truncated |
| 1800 | 282166.2359375 | 2/2 | accepted for this reproduced scenario |

The 1,300-token variant is faster than the two 1,800-token confirmations, but
it is not a valid optimization because both outputs were cut off. The current
production default must remain 1,800 unless another candidate is separately
shown to stop naturally and passes accuracy review. No accuracy score was
measured here.

## Proposed Phase 1 latency contract

A single end-to-end number would hide queueing and encourage another unsafe
output cutoff. The proposed contract is therefore multi-part:

| Dimension | Proposed acceptance target | Qualification |
| --- | ---: | --- |
| Job-enqueue HTTP response | p95 `<=2000 ms` | Four simultaneous sessions; endpoint persists and returns the job ID, not the answer |
| First durable progress event | p95 `<=3000 ms` | Measured from request start to the first SSE status/stage event |
| Fast Research isolation | p95 `<=5000 ms` | Mixed test of one Deep submission plus three simultaneous Fast requests |
| Correctness-safe Deep service time | p95 `<=300000 ms` | Queue time excluded; current 14B model, fixed stress scenario, `done_reason=stop`, no hidden HTTP timeout |
| One-Deep mixed-workload end-to-end | p95 `<=305000 ms` | One Deep plus three Fast sessions; includes enqueue/dispatch overhead |
| Cancellation acknowledgement | p95 `<=2000 ms` | Cancellation request accepted and durable job state changes; model-process release measured separately |

For multiple queued Deep jobs, the end-to-end contract should be
`queue_wait_ms + 300000 ms`, with queue position and elapsed time visible. With
one local model and bounded generation concurrency of one, promising every one
of four simultaneous Deep jobs a 300-second end-to-end completion would be
mathematically dishonest: the fourth job can wait behind three service periods.

The proposed `300000 ms` service-time target is not described as an achieved
p95. It is a Phase 1 acceptance target to be tested with a larger repeated
sample after job execution and progress instrumentation exist. The current two
correctness-safe observations (`268594.616917` and `295737.854958 ms`) fit below
that ceiling, with only `4262.145042 ms` between the slower observation and the
proposed limit. Any regression beyond the target must be reported, not rounded
down or hidden by asynchronous delivery.

## Recommendation

Retire the 60-second completion requirement for the current local 14B profile.
Keep the 3-second visible-progress goal, adopt 300 seconds as the provisional
correctness-safe Deep **service-time** ceiling for the fixed stress workload,
and preserve the five-second Fast isolation target. A future sub-60-second Deep
goal requires a measured model/quantization or pipeline change plus the legal
accuracy evaluation; job queues and SSE alone cannot produce it.

No Phase 1 implementation should begin until the user approves or revises this
contract.
