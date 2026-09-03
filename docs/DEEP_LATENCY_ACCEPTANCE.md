# Deep Review Phase 1 latency acceptance

**Evidence date:** 31 August 2026  
**Decision:** **NOT ACCEPTED — Phase 1 remains open**

## Approved contract

| Gate | Accepted value |
|---|---:|
| Enqueue p95 | <= 2,000 ms |
| First durable progress p95 | <= 3,000 ms |
| Fast p95 in one-Deep/three-Fast scenario | <= 5,000 ms |
| Correctness-safe Deep service p95, excluding queue | <= 300,000 ms |
| One-Deep/three-Fast end-to-end | <= 305,000 ms |
| Cancellation acknowledgement | <= 2,000 ms |
| Additional queued Deep job | queue wait + 300,000 ms |

## Current exact-build mixed evidence

Source: `docs/evidence/phase1-mixed-load-run-09.json`.

| Metric | Observed value | Decision |
|---|---:|---|
| Enqueue HTTP | 16.737542 ms | Pass for this run |
| First durable progress | 536.505708 ms | Pass for this run |
| Fast p95 | 92.944966 ms | Pass |
| Deep end-to-end | 235,215.636292 ms | Pass |
| Deep workflow | 233,746.464148 ms | Pass |
| Deep terminal status | succeeded | Pass |
| Deep citations | 2 | Pass |
| Missing-pet Fast result | 0 citations / insufficient evidence | Correct safe abstention for this corpus |

The answer was structured, source-referenced, contained the professional disclaimer, did not expose `RAG` or `chunk` language, and appended a source-currency warning because current status was not verified.

## Queued Deep evidence

Source: `docs/evidence/phase1-queued-deep-run-01.json`.

| Position | Enqueue | Queue wait | Service | End-to-end | Status | Citations |
|---:|---:|---:|---:|---:|---|---:|
| 1 | 33.977083 ms | 182.095 ms | 332,972.397 ms | 333,154.492 ms | succeeded | 2 |
| 2 | 12.909541 ms | 333,166.63 ms | 209,936.002 ms | 543,102.632 ms | succeeded | 2 |

The second job passed the queue contract because 543,102.632 ms is below its 333,166.63 ms queue wait plus 300,000 ms allowance.

The two observed service values are 209,936.002 ms and 332,972.397 ms. Using the same linear percentile method as the benchmark scripts, service p95 is **326,820.57725 ms**. This exceeds the 300,000 ms ceiling by 26,820.57725 ms. Phase 1 cannot close.

## Cancellation evidence

| Evidence | Cancel HTTP | Terminal cancellation |
|---|---:|---:|
| `phase1-cancellation-run-01.json` | 55.515917 ms | 297.905 ms |
| `phase1-cancellation-run-02.json` | 39.985959 ms | 538.624 ms |

Both observed terminal acknowledgements are below 2,000 ms.

## Preserved failed findings

- `phase1-mixed-load-run-03.json`: the earlier free-form answer prompt produced zero exact citation markers and correctly abstained. This prompted the schema-constrained claim contract.
- `phase1-mixed-load-run-06.json`: cold simultaneous Fast p95 was 8,713.101475599999 ms.
- `phase1-mixed-load-run-07.json`: BGE query micro-batching made all three Fast requests similarly slow; p95 was 8,489.1959869 ms.
- `phase1-mixed-load-run-08.json`: the first lexical Fast lane reached p95 123.07622049999999 ms but abstained on all three questions, so it was not accepted as useful.
- The final lexical lane adds local-window relevance and distinctive-concept anchors. Run 09 produced four citations for FIR, four for Article 14 and a safe zero-citation abstention for the unsupported missing-pet question.

## Test evidence

The final backend regression run observed **129 passed, 1 warning in 21.24 seconds**. The warning is the existing Passlib import of Python's deprecated `crypt` module. No test failed.

## Qualification and next action

Durable jobs, saved SSE progress, cancellation, bounded Ollama concurrency, rate limits, structured verified Citizen answers and mixed Fast responsiveness are implemented. The only measured acceptance breach in the current ledger is correctness-safe Deep service p95 under two queued jobs.

Before closing Phase 1, rerun the queued benchmark after reducing local generation/verification service time without lowering the source-verification standard. Preserve this record and write a new raw evidence file; do not overwrite the failed measurement.
