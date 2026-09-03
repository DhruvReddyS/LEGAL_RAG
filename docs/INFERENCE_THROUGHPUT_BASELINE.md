# Inference throughput baseline

**Measured:** 3 September 2026
**Host:** MacBook Pro, Apple M5 Pro, 18 cores (6 Super + 12 Performance), 24 GB unified memory, macOS 27.0
**Harness:** [`scripts/ollama_throughput_baseline.py`](../scripts/ollama_throughput_baseline.py)
**Raw evidence:** [`evidence/ollama-throughput-m5pro-14b-ctx16384.json`](evidence/ollama-throughput-m5pro-14b-ctx16384.json), [`evidence/ollama-throughput-m5pro-4b-ctx8192.json`](evidence/ollama-throughput-m5pro-4b-ctx8192.json)

## Correction to the prior attribution

Earlier notes attributed the ~10 tokens/second generation rate to a CPU-bound
configuration, and a proposed remediation was to move Ollama out of Docker so
it could reach Metal.

**That attribution was wrong.** Ollama has been running natively on the host
throughout (`/Applications/Ollama.app/Contents/Resources/ollama serve`, bound to
`127.0.0.1:11434`). The `ollama` service in `docker/docker-compose.yml` sits
behind the `llm` profile and is opt-in; `OLLAMA_BASE_URL` already resolves to
the host. `ollama ps` during these measurements reports:

```text
NAME                    ID              SIZE     PROCESSOR    CONTEXT
qwen3-14b-16k:latest    351c0a45b605    11 GB    100% GPU     16384
```

The model is, and was, fully GPU-resident. There is no Metal passthrough
problem to solve.

## Measurements

`qwen3-14b-16k` (14.8B parameters, Q4_K_M, 9.3 GB on disk, 11 GB resident),
`num_ctx` 16384, model warm, `temperature` 0.0:

| Prompt tokens | Prefill | Prefill tok/s | Decode tok/s |
| ---: | ---: | ---: | ---: |
| 619 | 1.69 s | 366.5 | 14.36 |
| 7,704 | 31.64 s | 243.5 | 13.56 |
| 15,374 | 45.42 s | 338.5 | 11.75 |

`qwen3:4b` (2.5 GB, 3.8 GB resident), `num_ctx` 8192, candidate small tier:

| Prompt tokens | Prefill | Prefill tok/s | Decode tok/s |
| ---: | ---: | ---: | ---: |
| 613 | 0.52 s | 1,171.7 | 44.68 |
| 7,698 | 10.96 s | 702.6 | 32.85 |

An exploratory run of the 14B at `num_ctx` 8192 showed no throughput benefit
over 16384; both configurations are 100% GPU-resident. That run included a
model reload on a non-idle host and is not recorded as evidence. The finding is
"no benefit observed", not "8192 is slower".

## What this explains

Decode throughput falls as the KV cache grows: 14.4 tok/s at a 619-token
prompt, 11.8 tok/s at 15,374. The 9.6–11.9 tok/s recorded in
[`DEEP_LATENCY_TARGET_CALIBRATION.md`](DEEP_LATENCY_TARGET_CALIBRATION.md) was
measured at 6,496- and 12,893-token prompts, so it is the expected rate at
those sizes rather than evidence of a misconfiguration.

Prefill is the larger and less visible cost. At ~250–340 tok/s, the
12,893-token verification prompt spends roughly 40–50 seconds before emitting a
single token, which matches the 42.0 s time-to-first-token recorded in
`evidence/phase1-mixed-load-run-09.json`.

**The lever is prompt and output size, not device placement.**

## Bearing on the Deep latency target

Applying these rates to the accepted Deep run (295.7 s):

| Stage | Recorded | Projected after prompt/output discipline |
| --- | ---: | ---: |
| query_understanding | 18.6 s | 0–3.4 s (skipped when self-contained, else small tier) |
| retrieval | 20.1 s | 5–20 s — **unmeasured**, depends on the reranker device |
| reasoning | 162.6 s | ~86 s (6,496 tok prefill + 700 output tok) |
| verification | 94.4 s | ~29 s (premise capped to ~4,000 tok) |
| **Total** | **295.7 s** | **120–138 s** |

This does not reach a 90-second target. Closing the remaining 30–48 s would
require shortening reasoning output far enough to risk answer coverage, moving
verification to the small tier (prohibited — verification must stay on the 14B),
or overlapping verification with reasoning so claims are checked as they are
emitted. Only the third costs no correctness.

The retrieval row is the largest remaining unknown, and it is why the resolved
inference device is now logged at startup and reported on `/health/ready`.
