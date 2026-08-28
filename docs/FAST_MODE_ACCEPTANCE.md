# Fast Research Mode — Acceptance Report

Verified: **26 August 2026 IST**

## Outcome

Fast Research mode is implemented and accepted as a retrieval-first evidence
brief. It is intentionally different from Deep Review: it makes no generative
legal claims, skips the expensive BGE cross-encoder and LLM chain, and publishes
only reviewable Gold-corpus passages that pass a conservative subject-matter
gate.

The five-second target applies to a complete Fast response, not merely first
token. After moving model loading into backend readiness, the first uncached
user query completed in **412.54 ms** with four citations.

## Architecture

```text
authenticated query
  -> response_mode=fast
  -> hashed in-memory query-embedding cache
  -> BGE-M3 dense + learned sparse query embedding
  -> parallel Qdrant dense, sparse and RRF queries
  -> conservative lexical subject-matter gate
  -> source-led Gold evidence brief or explicit abstention
  -> citations + stage timings + target status + audit event
```

Fast mode does not call query-understanding, reasoning, verification or response
generation LLM nodes. Deep mode continues to use the accepted bounded LangGraph
workflow unchanged.

## Live measurements

Hardware/profile: 24 GB Apple Silicon host, Docker backend using CPU BGE-M3,
25,517-point Gold collection, concurrency 1.

### Before startup warm-up

| Run | Embedding | Qdrant | API total | Result |
| --- | ---: | ---: | ---: | --- |
| Cold model | 7,565.96 ms | 43.03 ms | 7,620.28 ms | target missed |
| Identical cached query | 0.02 ms | 7.45 ms | 10.97 ms | target met |
| Identical cached query | 0.01 ms | 5.33 ms | 8.97 ms | target met |

The cold miss was corrected by loading the query embedder before the backend is
declared ready. Backend readiness takes approximately ten seconds after a fresh
container start; user traffic no longer pays the model-load cost.

### Warm model, five different legal questions

| Query family | Wall time | Embedding cache | Target |
| --- | ---: | --- | --- |
| FIR registration | 20.27 ms | hit | met |
| Bail procedure | 367.85 ms | miss | met |
| Article 14 | 449.42 ms | miss | met |
| Contract essentials | 434.00 ms | miss | met |
| Missing dog edge case | 447.24 ms | miss | met |

Mean: **343.76 ms**. Interpolated p95: **448.99 ms**. Five-second target-met
rate: **100%**.

After a container restart with startup warm-up enabled, a fresh uncached query
completed in **412.54 ms**: 364.87 ms embedding, 26.11 ms Qdrant, four citations,
target met.

## Accuracy correction found by browser QA

The initial missing-pet query retrieved missing-child authorities because both
contained the word "missing". Although the response completed in 0.52 seconds,
the subject matter was not acceptable. A conservative focus-token coverage gate
was added and regression-tested.

Final browser result for:

> How should I report a missing pet dog, and when can an FIR be requested?

Fast mode returned the explicit insufficient-evidence state in **0.40 seconds**,
with zero citations and a visible safe-abstention badge. It no longer publishes
the missing-child sources for that query. The Deep workflow remains available
when synthesis or broader analysis is required.

## API contract

Request:

```json
{
  "query": "Is FIR registration mandatory for a cognizable offence?",
  "response_mode": "fast"
}
```

The response now includes `response_mode`, `timings_ms`,
`latency_target_ms`, and `target_met`. Deep requests use
`"response_mode": "deep"`; omitted mode remains Deep for backward
compatibility.

HTTP responses also expose a validated `X-Request-ID` and `Server-Timing`
header. Logs contain request ID, route, status and duration without query text,
tokens or credentials.

## Reproduce the benchmark

Use a dedicated local benchmark account. The password is read from an
environment variable and never written to the report:

```bash
export LEGAL_RAG_BENCHMARK_PASSWORD='set-a-dedicated-test-password'
.venv-ingest/bin/python scripts/chat_latency_benchmark.py \
  --email benchmark@example.com \
  --mode fast \
  --warmup 1 \
  --runs 10 \
  --concurrency 1 \
  --output data/legal_kb/logs/fast-latency.json
```

Do not use a production user or production password for benchmarking.

## Verification

- Complete final backend suite: **80 passed**; final focused
  performance/relevance suite: **9 passed**.
- Next.js 14 type check and production static export: passed.
- Docker PostgreSQL, Qdrant, MinIO and backend: healthy.
- Authenticated desktop browser workflow: passed.
- Fast/Deep selector, timing badge, target badge, citation panels and safe
  abstention state: verified in the running UI.
- All disposable benchmark/UI test users were deleted after testing. Browser QA
  questions remain in the existing user's local research history as test
  evidence.

## Remaining performance backlog

1. Redis-backed cross-replica result cache with owner/role/case/corpus-version
   scope in every private cache key.
2. Server-Sent Events for Deep time-to-first-token and cancellable requests.
3. Compact-model bakeoff for an optional synthesised Fast answer; the current
   accepted Fast mode remains retrieval-only until quality gates pass.
4. Concurrency benchmarks at 5, 10 and 25 and bounded inference backpressure.
5. Prometheus/OpenTelemetry export and a production latency dashboard.
6. Versioned corpus release aliases and cache invalidation on promotion.
