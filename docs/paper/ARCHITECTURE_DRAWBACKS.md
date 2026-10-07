# Corpusil — Architectural Drawbacks

Design-level weaknesses, found by reading the code on 2026-10-08. These are distinct
from the evaluation gaps in §7 of the architecture plan: those are missing evidence,
these are properties of the system as built.

Ordered by how much they cost and how citable they are.

---

## 1. A semantic retriever gated by a lexical filter — the central flaw

**Where:** `services/fast_research.py:237–262`

```
COVERAGE_FLOOR                    = 0.34
COVERAGE_FLOOR_WITHOUT_RARE_TERM  = 0.45
```

`_lexical_coverage()` is the fraction of the query's focus tokens that appear
**literally** in a passage window. Matching extends to safe plural base forms and
nothing else: no synonymy, no morphology, no embedding. A passage must contain 34–45%
of the user's own words or it is discarded.

This sits **downstream of BGE-M3 hybrid retrieval**, whose entire purpose is to bridge
vocabulary. Dense retrieval finds that *"a shop refused to replace my broken phone"*
is about deficiency in service. The gate then throws that result away, because the
statute says "deficiency in service" and the citizen said "shop", "refused", "broken",
"phone" — overlap near zero.

**This is the architectural cause of the consumer and online-harassment refusals.** The
~300 relevant passages per topic are retrieved and then rejected. It also explains why
the earlier lay-vocabulary bridge failed: it was wired into query understanding and then
into the retrieval boundary, but the gate is what was doing the rejecting.

The gate is not wrong to exist — the comment above it is correct that it is the only
thing between an unanswerable question and a plausible answer assembled from adjacent
material. It is wrong in *kind*: an abstention decision is being made on lexical
evidence by a system whose retrieval is semantic.

**Fix:** make the gate operate in the same space as the retriever. Options, cheapest
first: (a) score coverage against the dense similarity between query and passage with a
calibrated threshold; (b) a small NLI check "does this passage address this question";
(c) keep the lexical floor but apply it to the *expanded* query, after a legal-term
normalisation step. The existing `legal_term_normalization.py` and the reverted
`lay_vocabulary.py` are the materials for (c).

**Why it matters for the paper:** abstention is presented as a contribution. A reviewer
who reads the gate will see that the abstention criterion and the retrieval criterion
disagree by construction, and the false-refusal rate is unmeasured.

---

## 2. Self-verification — the model grades its own work

**Where:** `agents/verification_agent.py:126` — `verification_node(state, llm: OllamaClient)`

The verification agent is a genuine NLI-style entailment check: each claim is tested
against the premise text of the chunk it cites, and returns yes / partial / no. That is
a real design, better than a citation-presence check.

But it calls **the same `qwen3-14b-16k` that generated the answer**, at the same
temperature. Self-verification is a known-weak signal: a model that produced a claim is
disposed to judge that claim entailed. The verification stage can therefore be expected
to catch formatting and attribution errors reliably, and *semantic* overreach much less
reliably — which is the failure the system is built to prevent.

**Fix:** verify with a different model, or with a non-generative entailment model
(a small cross-encoder NLI head is cheap and sidesteps the ~85 s generation cost
entirely). Either way, report verifier agreement against human judgement on a sample —
that measurement does not exist today.

## 2b. Premise truncation at 1,800 characters

**Where:** `verification_agent.py:20`, applied at line 132.

The premise shown to the verifier is cut at 1,800 characters. A claim supported by text
beyond that point is judged unsupported and triggers a retry or an abstention. Statutory
provisions with long enumerations — exactly the ones that matter — are the most likely
to exceed it. The truncation is silent and unmeasured.

---

## 3. Throughput ceiling of one

**Where:** `llm.py:62` — `asyncio.Semaphore(ollama_generation_concurrency)`, default **1**;
`config.py:71` — `sync_deep_requests_per_minute` default **2**.

The system generates **one answer at a time**, process-wide. The synchronous deep budget
of 2/min is the configuration conceding it. The async job worker relieves the user
experience but not the ceiling: it queues, it does not parallelise.

For a single-machine demo this is correct and honest. As a claim about a platform
serving police, advocates and citizens concurrently, it is the weakest point in the
design, and it is architectural rather than a tuning value — there is no generation
worker pool to raise.

**Fix for the paper:** either report it as a stated limitation with a measured
queue-depth-versus-wait curve, or put generation behind a pool of workers and report
throughput at concurrency 2 and 4.

---

## 4. The citizen routing rule is coarse

**Where:** `services/adaptive_routing.py:59`

`role == "citizen"` → always Deep. This fixed a real problem: citizens were being handed
stacks of statute instead of answers. But it is unconditional, so a citizen asking
*"what is BNS section 103"* — a pure lookup with no synthesis to do — pays the full deep
pipeline, currently tens of seconds.

**Fix:** keep the rule but let an explicit single-provision lookup fall through to Fast
with a synthesised one-line gloss. The signals already computed in the same function
(`multiple_legal_provisions`, word count) give the test almost for free.

---

## 5. No degradation path when generation is unavailable

`llm.py` raises a typed error on connect failure, and callers handle it — but there is no
*architectural* fallback. If Ollama is down, the deep lane fails rather than degrading to
the fast lane, which needs no model at all and would still return correct authority.

For a system whose stated value is that users never hit a dead end, "the LLM is down so
you get nothing" is the wrong failure mode when a no-LLM lane is sitting right there.

---

## 6. Retrieval is one flat collection

`global_legal_corpus_v4` is a single Qdrant collection. A `corpus_tier` payload field
exists, but jurisdiction is not a routing dimension: an Andhra Pradesh query searches all
980 central Acts alongside the 38 AP ones. At 1,036 documents this is harmless. It is not
a design that extends, and the paper should not imply it scales untested.

---

## 7. Concordance is a static artefact

`section_mapping.json` holds **2,596 pairs** with provenance and review status — well
built, and more substantial than it first appears. But it is hand-curated and frozen. New
amendments require a human edit; there is no detection of a mapping that has gone stale.
State this as a maintenance assumption rather than letting a reviewer infer automation.

---

## 8. Confidence is reported but not reproducible

Confidence values are shown to users and vary run to run. Either the variance is
explained and bounded, or the number should not be presented as a measurement. This is
the cheapest item on the list and the most damaging if a reviewer notices it before you
mention it.

---

## Priority

| # | Drawback | Cost to fix | Value |
|---|---|---|---|
| 1 | Lexical gate on a semantic retriever | Medium | **Highest** — fixes live refusals *and* strengthens the abstention contribution |
| 2 | Self-verification | Medium | High — it undercuts the core claim |
| 8 | Confidence not reproducible | Low | High — cheap credibility |
| 3 | Concurrency 1 | High, or free if stated | Medium |
| 4 | Coarse citizen routing | Low | Medium — user-visible latency |
| 5 | No degradation to the fast lane | Low | Medium |
| 2b | Premise truncation | Low | Medium |
| 6, 7 | Flat collection, static concordance | — | State as limitations |

**If only one thing is done: fix #1.** It is the only item that simultaneously repairs a
live product failure, removes a contradiction a reviewer will find, and turns abstention
from an assertion into something measurable.
