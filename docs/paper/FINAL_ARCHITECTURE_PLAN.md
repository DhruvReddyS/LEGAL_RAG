# Corpusil — Final Architecture Plan

A multi-agent retrieval-augmented system for Indian law, serving four roles from one
corpus over two retrieval lanes.

Every figure below was read from the code or the data on 2026-10-08, and the file and
line are given so each can be rechecked. Where the running system differs from the
intended design, the plan says so rather than describing the intent as if it shipped.

---

## 1. The design problem

A legal question has two honest answers and they need different machinery.

*"What does BNS section 103 say?"* wants the provision, fast, unembellished. Synthesis
adds nothing and risks paraphrasing a statute into something it does not say.

*"My landlord kept my deposit, what can I do?"* wants a synthesised answer — but only if
the corpus actually supports one. A fluent answer built on nothing is the single worst
failure this system can produce, because it is indistinguishable from a good one to the
person who most needs it.

So the architecture is organised around one commitment: **a claim that is not traceable
to a retrieved chunk does not get published.** Everything else — the two lanes, the
verification agent, the coverage gate, the bounded retry — exists to serve it.

---

## 2. Layers

### 2.1 Clients

One Next.js 14 / React 18 frontend, delivered two ways: in a browser, or inside a Tauri
desktop shell. Both talk to the same API. **Any role can use either client** — the client
is not a role boundary.

### 2.2 API gateway

FastAPI, **15 routers** (`backend/app/routers/`): `admin`, `auth`, `authorities`,
`cases`, `chat`, `citizen_intake`, `document_analysis`, `documents`, `feedback`,
`ingestion`, `investigation`, `jobs`, `retrieval`, `storage`, `strategy`.

JWT access + refresh with revocation (`token_revocation.py`), RBAC, and four separate
rate-limit budgets (`config.py`): fast 30/min, synchronous deep 2/min, job enqueue 6/min,
login 8/min globally and 5/min per account. The login limits are deliberate — bcrypt
verification is expensive by design, which makes an unthrottled login endpoint both a
credential-guessing target and the cheapest denial-of-service surface in the application.

### 2.3 Routing

`adaptive_routing.route_legal_query()` decides the lane. **No LLM is involved** — it is
deterministic, which means it is testable and its decision is explainable in a sentence.

Precedence:

1. An explicit `fast` or `deep` from the user wins outright.
2. **Role next: `citizen` → always Deep.** A citizen asking a question needs a
   synthesised answer, not a stack of statutes to read. This is the rule that made the
   citizen module work.
3. Otherwise, signals escalate to Deep: a case-scoped matter; an unresolved backreference
   when history exists; ≥36 words; ≥2 question marks; ≥2 cited provisions; or a match
   against the deep-intent patterns.
4. No signals → Fast.

The backreference rule earns its place. Asked *"what about for a woman?"* after a
question about arrest, Fast — which is given no history — searched for "woman" and
answered about women in general: fluent, grounded, and about the wrong thing.

### 2.4 The Fast lane — `services/fast_research.py`

Hybrid dense + sparse retrieval over Qdrant with server-side RRF fusion, a coverage gate,
and ranked passages returned as-is.

**The Fast lane calls no LLM and no reranker** (`fast_research.py:408`). That is the
whole point: it returns the authority for a professional to read, so there is no
generation step that could misrepresent it. Defaults: 8 candidates, 4 results, 5,000 ms
target (`config.py`).

When the coverage gate finds nothing on point, the lane **abstains**. It does not
degrade to a weak answer.

### 2.5 The Deep lane — LangGraph, `agents/orchestrator.py`

```
role_context → query_understanding → retrieval ─┬─(reason)→ reasoning → verification ─┬─(proceed)→ response_generation → END
                                                │                                      │
                                                └─(skip)──────────────────────────────┐└─(retry)→ retry → retrieval
                                                                                      ▼
                                                                          response_generation
```

Five agents do the work (`backend/app/agents/`): `query_understanding`,
`retrieval_agent`, `reasoning_agent`, `verification_agent`, `response_generation`.

Two conditional edges carry the design:

- **After retrieval**, `skip` jumps straight to response generation when there is nothing
  worth reasoning over — the expensive stages are skipped, not repeated.
- **After verification**, `retry` loops back to retrieval, bounded at 2
  (`orchestrator.py:201`).

The retry bound is bounded by evidence as well as by count. From the code's own comment:
a broadened query that returns evidence the previous pass already saw will, at
temperature 0, produce the same claims and the same verdicts — one measured run spent
**84 seconds, a quarter of its total**, re-deriving a byte-identical result before
abstaining anyway. So the system retries only when a retry can still change something.

### 2.6 Case and investigation work — police and advocate

Reached through the `cases`, `investigation` and `document_analysis` routers. Three are
true agents, two are services, and the distinction is worth keeping straight:

| Capability | Where it lives | Kind |
|---|---|---|
| Document analysis | `services/document_analysis.py` | service |
| Drafting (FIR, notice, petition) | `agents/drafting_agent.py` | **agent** |
| Timeline against statutory clocks | `services/investigation_timeline.py` | service |
| BNSS compliance | `services/investigation_compliance.py` | service |
| Defence strategy | `agents/defence_strategy_agent.py` | **agent** |
| Publication / export | `agents/publication.py` | **agent** |

### 2.7 Data and models

- **Qdrant 1.18** — `global_legal_corpus_v4`, dense 1024-d + sparse lexical, server-side
  RRF.
- **PostgreSQL 16** — 19 ORM models (`backend/app/models/`): cases, chat, corpus, jobs,
  investigation, audit.
- **MinIO** — uploaded documents and generated artefacts.
- **BAAI/bge-m3** — embeddings, 1024-d, dense and sparse from one model.
- **Ollama `qwen3-14b-16k`** — temperature 0, generation concurrency 1, 30-minute
  keep-alive so the first Deep request after a short idle does not pay to reload it.
- **Job worker** (`services/job_worker.py`) — long work runs asynchronously, 500 ms poll.

Legal-correctness services sit alongside retrieval: `section_mapping` (IPC/CrPC/IEA →
BNS/BNSS/BSA concordance), `currency`, `repeal_labels`, `citation_following`,
`authority_check`, `section_confidence`.

Repealed provisions are not hidden — they are **rank-penalised by 3 places**
(`repealed_rank_penalty`). Expressed in ranks rather than score on purpose: the ordering
key is an RRF score in Fast and a cross-encoder logit in Deep, which are not on the same
scale, so a multiplicative penalty would mean two different things in the two lanes.

### 2.8 Corpus

**1,036 canonical documents** (`data/legal_kb/metadata/canonical_documents.jsonl`):

| Jurisdiction | Documents |
|---|---|
| India — Central | 980 |
| India — Andhra Pradesh | 38 |
| India — Telangana | 18 |

33 staged, 90 quarantined. Quarantine is a feature: documents that fail script
dominance, authority verification or classification are held back rather than indexed.

---

## 3. Two decisions that look like gaps and are not

**The cross-encoder reranker is disabled.** `BAAI/bge-reranker-v2-m3` is integrated and
`cross_encoder_reranking_enabled` defaults to **False** (`config.py:62`).

The decision is correct, but the reason recorded in the code is not. The comment states
that **R@1 falls from 0.69 to 0.64**. At n = 48 that is **33/48 against 31/48 — a net of
two items**. Wilson 95% intervals are [0.55, 0.80] and [0.50, 0.77]; they overlap almost
entirely. Exact McNemar over every discordance split consistent with a net of two gives
**p ≥ 0.50**. There is no measurable accuracy difference in either direction, and the
honest statement is *"no significant accuracy gain"*, not *"accuracy falls"*.

What does survive scrutiny is the cost: **5,126 ms per query where fusion alone costs
91 — a factor of 56.** A component that costs 56× for no demonstrable accuracy benefit
should be off, and that argument stands on its own without the accuracy claim. It is a
setting rather than a deletion, so re-enabling it is a restart and the next corpus can be
measured with it rather than argued about.

*Action for the paper: restate this in `config.py:62` before submission. As written it is
a claim of effect from a two-item difference, which is the first thing a reviewer will
test.*

**Gemini Flash is configured first in the tier order and is not wired.** There is no
Gemini key in the environment. Ollama serves every request today. The tiering is designed
and unbuilt, and the diagram says so.

Both are defensible positions. Neither should be presented as working.

---

## 4. What the architecture guarantees

1. A published claim maps to a retrieved chunk. Verification enforces it; the retry loop
   is the second chance, not a way around it.
2. **Abstention is a valid output.** Fast abstains at the coverage gate, Deep abstains
   after bounded retry.
3. Lane selection is deterministic and explainable.
4. Repealed law is labelled and demoted, never silently dropped.
5. Role is enforced at the gateway, not in the client.

---

## 5. Honest status

| Area | State |
|---|---|
| Retrieval, both lanes | Working |
| Citizen synthesis path | Working |
| Case / investigation tooling | Working |
| Corpus, 1,036 docs | Indexed as v4 |
| Golden set | 21 items (v1), **61 items (v3)** — too small for significance |
| Cross-encoder rerank | Integrated, measured, **off** |
| Gemini tier | Configured, **not wired** |
| Deep-lane latency | ~85 s on a 24 GB machine where Ollama and Docker contend for memory |

### Known weaknesses, stated plainly

- **Latency is a hardware story, not an architecture story.** ~85 s per deep answer is
  memory pressure on a 24 GB machine, not a pipeline defect. It should be measured on
  hardware that does not swap before any pipeline work is done in its name.
- **~575 India Code Acts are downloaded and not yet ingested.** The corpus is 1,036
  documents, not the ~1,600 the raw material supports.
- **Some citizen questions still refuse.** Landlord/deposit refuses *correctly* — there
  is no rent or tenancy law in the corpus. Consumer and online-harassment questions
  refuse *despite* roughly 300 relevant passages each, which is a genuine retrieval
  failure and the most worthwhile thing to fix next.
- **No statistical activation gate.** With 61 golden items a corpus swap is judged on
  too few observations to be significant.
- **Confidence scores are not reproducible run to run.** Reported, so they should be.

---

## 6. Next steps, in priority order

1. Diagnose the consumer and online-harassment retrieval failures — passages exist and
   are not being found, which is a bug, not a corpus gap.
2. Ingest the remaining India Code Acts (hours; saturates the source API).
3. Measure Fast and Deep latency on non-swapping hardware before optimising anything.
4. Grow the golden set past 61 and define an activation gate with a significance
   threshold.
5. Make confidence reproducible, or stop reporting it as a number.
6. Wire the Gemini tier, or remove it from the design and say Ollama is the design.

---

---

## 7. IEEE publication readiness

Assessed against what a reviewer will actually check. **The architecture is sound and the
system is real; the evaluation is not yet publishable.** The gap is evidence, not design.

### Ready

- The architecture itself: the contribution — deterministic lane selection, a
  verification agent that gates publication, abstention as a first-class output — is
  coherent, implemented, and defensible.
- Reproducibility of the *system*: exact model identifiers, dimensions, temperature,
  concurrency, retry bounds and rate limits are pinned in `config.py` and quoted here.
- **Fig. 1** (`docs/paper/fig1-architecture.svg`): 7.16 × 5.12 in, two-column width,
  grayscale, Times, no colour-dependent encoding, all type ≥ 6 pt, verified free of
  crossings and label overflow. Caption in `FIG1_CAPTION.txt`.

### Not ready — in the order a reviewer will raise it

1. **No baselines.** There is no comparison against BM25-only, dense-only, or
   fusion-without-concordance. Without one, no retrieval claim can be made at all. This
   is the single blocking item.
2. **No ablations for the stated contributions.** The verification agent, the coverage
   gate and role-aware routing are presented as the novelty. Each needs a run with it
   removed. Absent that, the paper asserts rather than demonstrates.
3. **n = 61 is too small for the claims.** At this size a difference must exceed roughly
   8–10 items to reach significance. Every comparison must therefore report an interval
   and a test, and the rerank result above shows what happens when it does not.
4. **Latency numbers are confounded.** ~85 s per deep answer was measured on a 24 GB
   machine where Ollama (11.7 GB) and the Docker VM (7.7 GB) contend and the host swaps.
   This number cannot appear in a paper. Re-measure on hardware that does not swap, and
   report p50/p95 over the full golden set, not a single observation.
5. **Ground truth provenance is unstated.** Who authored the 61 items, against what
   criteria, and with what inter-annotator agreement? For a legal corpus a reviewer will
   ask whether a domain expert was involved.
6. **Confidence scores are not reproducible run to run** yet are reported to the user.
   Either make them deterministic or stop presenting them as a measurement.
7. **Corpus is described but not characterised.** 1,036 documents across 38 official
   publishers, 980 central / 38 AP / 18 TG, 90 quarantined — the paper needs the
   quarantine criteria and the duplicate-detection method stated, since both affect the
   denominator of every retrieval metric.

### What this costs

Items 1–3 are the real work and they are one experiment, not three: a single harness that
runs the golden set across {BM25, dense, fusion, fusion+rerank} × {verification on, off}
and emits per-condition recall with intervals. Items 4–7 are reporting discipline and are
cheap once that harness exists.

**Verdict: the architecture section would survive review. The evaluation section does not
exist yet, and no amount of work on the figure changes that.**

---

*Companion artefacts:* `docs/presentations/corpusil-clean.svg` (single-slide diagram,
verified free of crossings), `docs/presentations/Corpusil_Architecture_Slide.pptx`
(13.333 × 7.5 in, generated from the same coordinates).
