# Adaptive Corrective Hybrid RAG — Acceptance

Date: 26 August 2026 (Asia/Kolkata)

## Outcome

The research API and UI now support an auditable `auto` mode. It keeps focused
authority lookups on the accepted sub-five-second retrieval path and routes
case-scoped or analytically complex questions to the bounded multi-agent Deep
workflow. Explicit Fast and Deep choices are never overridden.

This routing is deterministic and adds no model call or network hop. The API
returns the requested mode, selected mode, reason and routing signals; the same
decision is stored in the audit log and appended to the agent trace.

## Implemented retrieval controls

1. BGE-M3 dense and sparse query vectors with Qdrant reciprocal-rank fusion.
2. Hashed in-process embedding LRU cache and startup model warm-up.
3. Fast-path lexical subject gate to reject topically misleading passages.
4. Retrieval over a wider candidate set followed by distinct-document-first
   selection, preventing near-duplicate chunks from occupying every citation.
5. Source-led Fast brief with no generative claims and explicit abstention when
   adequate Gold evidence is unavailable.
6. Deep LangGraph workflow retained for reasoning, citation verification and
   bounded correction when the query actually requires analysis.

## Auto routing policy

Auto selects Deep for a case-scoped matter, a long multi-fact prompt, multiple
questions or provisions, defence/strategy work, evidence contradictions,
comparative reasoning, legal drafting, and precedent-application tasks. A
focused legal lookup selects Fast. The UI explains which route was selected.

The policy is intentionally inspectable. It avoids using a second LLM merely
to decide which LLM workflow to use, eliminating router latency, extra cost and
another nondeterministic failure point.

## Verification evidence

- Adaptive routing and Fast retrieval focused tests: **9 passed**.
- Compose-environment backend suite excluding two image-packaging-only script
  imports: **78 passed, 1 unrelated MinIO presigned-URL environment failure**.
- Next.js 14 type check and production static export: **passed**.
- Docker backend, PostgreSQL, Qdrant and MinIO: **healthy**.
- Live disposable-user Auto API query: requested `auto`, selected `fast`,
  `focused_authority_lookup`, four distinct citations, moderate evidence,
  **594.22 ms API total**, target met. The disposable user was deleted.
- Authenticated browser Auto workflow: visible route explanation, four citation
  panels, **0.03 s warm cached API timing**, target met; end-to-end browser
  interaction completed in 1.651 s.

The full container test collection cannot currently be a single zero-exit
command because the backend image does not copy two root `scripts/` files, and
the in-container MinIO presigned URL points to host-local `localhost:9000`.
These are test-packaging/environment issues, not adaptive-RAG failures.

## API example

```json
{
  "query": "Is FIR registration mandatory for cognizable offences?",
  "response_mode": "auto"
}
```

Relevant response fields:

```json
{
  "requested_mode": "auto",
  "response_mode": "fast",
  "routing_reason": "focused_authority_lookup",
  "routing_signals": ["simple_focused_query"],
  "latency_target_ms": 5000,
  "target_met": true
}
```

Omitting `response_mode` remains backward-compatible and selects Deep. The web
application now defaults to Auto.

## Next ordered improvements

1. Build a 50–100-query legal golden set and measure Recall@k, MRR, nDCG,
   citation precision/coverage, abstention accuracy and p50/p95/p99 latency.
2. Add current-law/version filters and an official-source authority prior once
   the corpus currency review is complete.
3. Add Redis result caching scoped by user role, case, corpus release and mode.
4. Stream Deep workflow progress with cancellation and bounded inference queues.
5. Benchmark concurrency at 5, 10 and 25 users before changing worker counts.
6. Evaluate query expansion and HyDE only as measured Deep-mode variants;
   neither belongs on the accepted Fast path without an accuracy win.
