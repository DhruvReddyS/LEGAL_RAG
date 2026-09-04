# Citizen module — how it works, end to end

**Version:** 10 September 2026
**Scope:** Everything a citizen-role request touches, from the source PDF on disk to the rendered answer.
**Audience:** Anyone who has to explain, extend, or defend this system.

This describes what the code actually does. Where a design is a compromise, or a
component is weaker than its name suggests, it says so.

---

## Contents

1. [The shape of the system](#1-the-shape-of-the-system)
2. [Corpus construction: PDF → chunks → vectors](#2-corpus-construction-pdf--chunks--vectors)
3. [What a chunk carries](#3-what-a-chunk-carries)
4. [Request admission](#4-request-admission)
5. [Safety screening](#5-safety-screening)
6. [Routing: Fast or Deep](#6-routing-fast-or-deep)
7. [The Fast lane](#7-the-fast-lane)
8. [The Deep lane: the agent graph](#8-the-deep-lane-the-agent-graph)
9. [Retrieval in detail](#9-retrieval-in-detail)
10. [The LLM boundary](#10-the-llm-boundary)
11. [Verification: the core idea](#11-verification-the-core-idea)
12. [Assembling the answer](#12-assembling-the-answer)
13. [Escalation and durable jobs](#13-escalation-and-durable-jobs)
14. [Document upload](#14-document-upload)
15. [The interface](#15-the-interface)
16. [Where latency goes](#16-where-latency-goes)
17. [Honest limitations](#17-honest-limitations)

---

## 1. The shape of the system

A citizen asks a question in plain English. The system answers **only** from a
governed corpus of Indian legal material, and every published sentence traces
to a specific passage in a specific document at a specific page.

Three properties drive the design:

- **A citizen cannot check the answer.** An advocate can spot a wrong section
  number; a citizen cannot. So the system is built to abstain rather than guess.
- **Retrieval is not the same as grounding.** Finding a relevant passage does
  not mean the passage supports the sentence written about it. That gap is
  where most RAG systems hallucinate, and it is what the verification stage
  exists to close.
- **Grounding is not the same as appropriateness.** "Should I plead guilty" can
  be answered fluently from statute text, and every claim would be grounded. It
  still must not be answered.

```
                    ┌───────────────────────────────┐
  PDFs on disk  →   │  Ingestion (offline, batch)   │  →  Qdrant + manifest
                    └───────────────────────────────┘
                                                            │
  Citizen question                                          │
        │                                                   ▼
        ▼                                          ┌──────────────────┐
  Admission → Safety screen → Router ──fast──────→ │ Hybrid retrieval │ → evidence brief
                                  │                └──────────────────┘
                                  └──deep──→ LangGraph: understand → retrieve
                                                     → reason → verify → respond
```

---

## 2. Corpus construction: PDF → chunks → vectors

This runs offline, ahead of any request. `backend/app/ingestion/pipeline.py`
orchestrates it. Current corpus: **419 physical PDFs → 381 canonical documents
→ 25,517 chunks → 25,517 Qdrant points.**

### 2.1 The manifest is the source of truth

Nothing is ingested because it happens to be in a folder. Every document must
appear in `data/legal_kb/metadata/canonical_documents.jsonl` with provenance:
source URL, authority, category, SHA-256 checksum, page count, verification
status.

`iter_canonical_documents` yields **one** physical file per
`canonical_document_id`. This is how 419 files become 381 documents — the same
Act downloaded from two government URLs is one canonical document, deduplicated
by content hash, not filename.

### 2.2 Extraction, with OCR only where needed

`ingestion/extract.py` uses **PyMuPDF** to pull the native text layer page by
page, with `sort=True` so multi-column legal typesetting reads in the right
order.

A page is sent to OCR only when its native text is under
`minimum_page_characters` (40) — a scanned page, or an image-only page in an
otherwise digital PDF. OCR is **Tesseract** via `pytesseract` at 300 dpi with
`--psm 6` (assume a uniform block of text), which suits statute pages better
than the default layout analysis. OCR pages run on a thread pool because
Tesseract is CPU-bound and releases the GIL.

Of the current corpus: **100 documents needed OCR, 3,978 pages OCR-processed.**

The original page text is retained alongside the working text, so a later
extraction bug can be diagnosed without re-running OCR.

### 2.3 Structural parsing — why not fixed-size chunks

This is the part most RAG tutorials skip, and it is the main reason retrieval
quality here is workable.

Splitting legal text every N characters cuts sections in half and orphans
section numbers from the text they label. `ingestion/structure.py` instead
parses the document into **structural units** using type-specific regex
grammars:

**For Acts and Rules:**
- `PART / CHAPTER / SECTION / SCHEDULE / APPENDIX / ANNEXURE` headings
- Numbered sections: `14. Equality before law`
- Column-layout sections, where the number sits after leading text
- Subsections: `(1)`, `(2A)`
- Legal sub-units: `PROVIDED THAT`, `EXPLANATION`, `ILLUSTRATION`, `CLAUSE`

**For judgments**, a separate grammar recognises the rhetorical structure:
`FACTS`, `ISSUES`, `ARGUMENTS OF THE APPELLANT`, `ARGUMENTS OF THE RESPONDENT`,
`ANALYSIS`, `AUTHORITIES CITED`, `RATIO DECIDENDI`, `FINAL ORDER`.

Each unit carries its `heading_path` (the chain of enclosing headings), its
`section` and `subsection` labels, and its page range. So a retrieved chunk
knows it is "Section 14, in Chapter II, at page 7", not just "some text".

### 2.4 Chunking

`ingestion/chunker.py` takes structural units and emits chunks:

- **A structural unit under 700 whitespace tokens becomes exactly one chunk.**
  Most sections are, so most chunks are a whole legal provision.
- A longer unit is split into **700-token windows with 80-token overlap**. The
  overlap means a rule split across a boundary appears whole in at least one
  window.
- Windows are cut on **whitespace-token boundaries**, never mid-word.
- A chunk with no word characters at all (a page of dashes, an OCR failure) is
  dropped.

**Chunk IDs are content-addressed:**

```python
stable_input = f"{canonical_document_id}|{unit_index}|{piece_index}|{page_start}|{page_end}|{piece}"
chunk_id = "gold-chunk-" + sha256(stable_input).hexdigest()[:32]
```

Re-ingesting unchanged text produces identical IDs, so ingestion is idempotent
and a citation stays valid across re-runs. Change the text and the ID changes,
which is what you want — a citation should not silently point at different words.

### 2.5 Embedding — BGE-M3, one pass, two vectors

`ingestion/embedder.py` wraps **`BAAI/bge-m3`** through `FlagEmbedding`.

BGE-M3 is chosen because a **single forward pass produces both** a dense vector
and sparse lexical weights:

```python
encode_options = {
    "batch_size": len(batch),
    "max_length": 8192,
    "return_dense": True,
    "return_sparse": True,
    "return_colbert_vecs": False,
}
```

- **Dense:** 1024 dimensions, L2-normalised, CLS-pooled. Captures meaning — it
  matches "my landlord kept my deposit" to text about security deposits without
  a shared keyword.
- **Sparse:** token-id → weight, a learned term-weighting closer to BM25 in
  spirit. Captures exact tokens — "Section 154", "BNSS", "cognizable".
- **ColBERT vectors are disabled.** They would triple storage for a
  late-interaction reranking stage that a cross-encoder already covers better.

Details that matter:

- **No instruction prefix.** BGE-M3 needs none. A prefix copied from E5 or
  BGE-v1.5 would shift every query vector with no error. Asserted by check E-01.
- **`max_length: 8192` set explicitly**, not inherited. A library default of 512
  would silently truncate 700-word chunks. Asserted by E-05.
- **fp16 only on MPS/CUDA**, fp32 on CPU, where fp16 is slow and unstable.
- **MPS OOM recovery:** halve the batch, rebuild the model, retry; fall back to
  CPU for one stubborn item, then return to MPS.

### 2.6 Writing to Qdrant

`ingestion/qdrant_writer.py` writes one point per chunk to
`global_legal_corpus`:

- Point ID is `uuid5(NAMESPACE_URL, chunk_id)` — deterministic, so a re-run
  overwrites rather than duplicates.
- Named vectors: `dense` (1024-d, **Cosine**) and `sparse` (**IDF modifier**).
- Payload indexes on every field a filter can touch, so filtering never forces a
  collection scan.

The Cosine/IDF configuration is **asserted at startup** by
`_validate_vector_schema`; the app refuses to boot against a mismatched
collection.

### 2.7 Integrity

Ingestion is crash-resumable: file-locked checkpointing with per-document claim
files, so two workers cannot double-write. Every run reconciles chunk counts
against Qdrant point counts and writes `ingestion_report.md`. Current state:
**0 failed documents, 0 payload issues, 0 validation issues.**

`scripts/verify_retrieval_health.py` runs 12 checks over this whole path (see
[§9.6](#96-the-health-checklist)).

---

## 3. What a chunk carries

Every Qdrant payload:

| Field | Purpose |
|---|---|
| `chunk_id` | Content-addressed identity; what a citation points at |
| `text` | The passage |
| `title`, `act_name`, `section`, `subsection` | Legal identity |
| `heading_path` | Chain of enclosing headings |
| `page_start`, `page_end` | So a citation names a page a reader can open |
| `source_type` | `act`, `judgment`, `rule`, `sop`, … |
| `court`, `jurisdiction`, `decision_date`, `decision_year` | Judgment metadata |
| `is_current` | Whether the authority is in force |
| `is_superseded` | Whether a later instrument replaced it |
| `canonical_document_id`, `document_id`, `source_id` | Provenance |
| `corpus_tier` | `gold` (verified) or `extended` (admin-published) |
| `verified_official`, `quality_status` | Provenance grading |

**`is_current` is currently `false` for every document in the corpus.** All 419
manifest entries carry a status containing the word "verify", and both
`is_current` properties treat "verify" as not-verified. This is deliberate
conservatism, not a bug — but it means the system cannot yet state that a
provision is in force, and every Deep answer carries a currency caveat. See
[§17](#17-honest-limitations).

---

## 4. Request admission

`POST /chat/query` in `routers/chat.py`. Before any work:

1. **`TrustedHostMiddleware`** — the Host header must be explicitly allowed.
2. **`DesktopOriginSecurityMiddleware`** — any cookie-authenticated mutation
   needs a trusted `Origin`. This is a real CSRF defence; CORS alone does not
   stop a browser *sending* a credentialed request, only from reading the reply.
3. **`require_permission(CHAT_USE)`** — resolves the user from a bearer token or
   the `legal_rag_access` HttpOnly cookie, then checks a database role →
   permission join. Not a hardcoded role check.
5. **Session ownership** — an existing `session_id` must belong to the caller.
6. **Rate limiting** — per-user sliding window: 30/min Fast, 2/min synchronous
   Deep, 6/min job enqueue.
7. **Disconnect guard** — `run_while_connected` polls the client connection and
   cancels the workflow if the browser goes away, so an abandoned tab does not
   hold a generation slot for four minutes.

The user's message is persisted before any answer is attempted, so a crash mid-
pipeline still leaves a coherent conversation.

---

## 5. Safety screening

`services/citizen_safety.py`, before routing, retrieval or generation.

**This is deterministic code, not a prompt.** A model asked to self-police gives
a different answer to a reworded question, and fails silently. Two categories:

**Emergencies** — immediate violence, self-harm, an offence in progress, a child
at risk. The response is emergency numbers first (112, 1091, 1098, 14416, 1930)
and a plain statement that the service researches law but cannot send help. A
four-minute Deep review is the wrong answer to "he is hitting me right now" even
if it would be accurate.

**Out-of-scope requests** — decide-for-me ("should I plead guilty"), outcome
prediction ("will I win"), evidence interference, false statements. Refused with
a route to a human: NALSA legal aid on 15100, and the District Legal Services
Authority. Each refusal also says what the service *can* still do.

An emergency outranks a refusal when a message contains both.

**Detection is deliberately conservative.** A false refusal on a legitimate
question turns a service for people with no other access to legal information
into one that declines to help. The first draft intercepted "what does the law
say about suicide prevention" on a bare keyword — abetment of suicide is a real
charge under BNS s.108. Self-harm detection now requires **first-person
framing**, because someone in crisis writes in the first person. Seventeen
ordinary questions covering domestic violence, child marriage, suicide law and
bail are asserted to pass through untouched.

---

## 6. Routing: Fast or Deep

`services/adaptive_routing.py`. **No LLM in the routing path** — a router that
calls a model has already spent the latency it exists to save.

`fast` or `deep` requested explicitly is honoured. On `auto`, the query is
scanned for deep signals:

| Signal | Trigger |
|---|---|
| `defence_strategy` | defence, loopholes, counterarguments, weaknesses |
| `case_analysis` | case scenario, fact pattern, case strategy |
| `evidence_analysis` | contradictions, cross-examination, chain of custody |
| `comparative_reasoning` | compare, distinguish, both sides, pros and cons |
| `legal_drafting` | draft/prepare/write near FIR/petition/notice |
| `precedent_reasoning` | precedents/case law near apply/distinguish |
| `constitutional_applicability` | private employer, state action, horizontal application |
| `long_multi_fact_query` | ≥ 36 words |
| `multiple_questions` | ≥ 2 question marks |
| `multiple_legal_provisions` | ≥ 2 section/article references |

Any signal → Deep. No signal → Fast. A case-scoped matter always goes Deep.

---

## 7. The Fast lane

`services/fast_research.py`. **Be clear about what this is: an evidence brief,
not a synthesised answer.** It retrieves and cites; it runs no reranker and no
LLM.

It was lexical-only for a long time, because the dense path measured
**8,489 ms p95** on this hardware and blew the five-second target. Warm, and
with the reranker input capped, dense+sparse fusion now measures **~180–230 ms**
end to end, and the relevance difference was not marginal: asked to explain
Article 14, the lexical lane returned the Model Prison Manual, while RRF
returns the Constitution's Article 14 and a Supreme Court judgment construing
it. Escalations to Deep fell from 4/8 to 3/8 on the acceptance set.

That switch also carried a cost that took a golden set to find. The lexical
path is the only thing that computes which query terms are rare enough to be
required, and the lane kept reading that field after it had stopped travelling
that path. It arrived empty, the requirement became vacuous, and abstention
accuracy fell to 0.33 — four of six known corpus gaps answered rather than
declined. The lane now computes those terms itself.

How it works:

1. **Normalise legal terms.** One-edit Damerau-Levenshtein correction against
   known Act acronyms, so `pocos` → `POCSO`. Ambiguity refuses to correct: `bnss`
   is one edit from `bns`, so neither is rewritten.
2. **Extract focus tokens.** Strip function words and *presentation* vocabulary
   ("explain", "in plain language"), but **keep** corpus vocabulary. `police`,
   `report`, `law` and `legal` were previously stripped as stopwords, which left
   procedural questions with nothing to match on.
3. **Per-term Qdrant full-text scroll**, plus an exact count per term.
4. **Derive distinctive terms** by document frequency — a term appearing in few
   documents is discriminative, and becomes *mandatory*.
5. **Local-window coverage.** Score by the best 50-token window, not the whole
   chunk. Two query concepts hundreds of words apart in a long chunk is not
   relevance; this is what stops a missing-child passage matching a missing-pet
   question.
6. **Gate at 0.5 coverage** plus the mandatory distinctive term.
8. **Select diverse authorities** — one best passage per distinct document.

**Confidence** = `min(0.85, (0.7·mean_coverage + 0.3·focus_recall) ·
mandatory_match_rate)`. It is a lexical overlap measure, capped at 0.85, and the
interface labels it "Relevance preview", not confidence. Every Fast citation is
marked `verification_status="unverified"`, because Fast runs no verifier.

Fast ignores `role`, `case_id` and `history` by design. Private case evidence
must not surface in a lane with no verifier.

---

## 8. The Deep lane: the agent graph

`agents/orchestrator.py`, a compiled **LangGraph** state machine.

```
role_context → query_understanding → retrieval → reasoning → verification
                                        ▲                         │
                                        │                         ▼
                                        └────── retry ◄──── score < 0.5?
                                             (max 2)             │ no
                                                                 ▼
                                                        response_generation
```

Five working nodes plus a bounded retry. Each node appends to `agent_trace`
(what it decided) and `stage_metrics` (what it cost).

**On "12 specialist agents":** `role_profiles.py` selects one of three citizen
profiles — Procedure Navigator, Rights Explainer, Authority Finder — by keyword
match. The selection injects **two extra lines into the same prompt**. It does
not change routing, tools, or the graph. Describe them accurately as
role-conditioned prompting. The five graph nodes are the real contribution.

### 8.1 role_context

Picks the citizen profile: objective, response contract, safety boundary. The
citizen contract asks for plain language, a numbered checklist, required
documents, and when professional or emergency help is appropriate. Cost: ~0.1 ms.

### 8.2 query_understanding

Produces intent, entities, complexity and a standalone `retrieval_query` that
resolves references from conversation history.

**The LLM call is skipped when the question is already self-contained**: no
history, no attached document, no backward reference (pronoun, "that", "what
about", a leading conjunction), under 60 words. `_fallback_intent` extracts Act
and section references by regex and passes the normalised question through.

This saves ~18 seconds. The test is conservative in the other direction — *any*
history sends it to the model, because a wrong skip costs retrieval quality and
18 seconds is not worth that.

---

## 9. Retrieval in detail

`services/retrieval.py` and `agents/retrieval_agent.py`.

### 9.1 Hybrid search

Per collection, **three Qdrant queries run concurrently**:

1. Dense-only (for score attribution)
2. Sparse-only (for score attribution)
3. **Server-side RRF fusion** over dense and sparse prefetches — this produces
   the actual ranking

**Reciprocal Rank Fusion** combines two rankings by summing `1/(k + rank)`
across lists. It is rank-based, not score-based, which is what you want when the
two scores are on incomparable scales. The `k` constant is Qdrant's internal
default and is not exposed through this API, which is why the Qdrant image is
pinned (`v1.18.2`) — an unpinned tag could move the constant under a recorded
evaluation.

Dense and sparse scores are kept per hit for the trace, so a result's provenance
is inspectable.

### 9.2 Oversampling and deduplication

Candidates are fetched at **3× the final limit**, then near-duplicates are
collapsed *before* reranking:

- 5-word **shingles**, **Jaccard similarity ≥ 0.88**
- Clustering is **keyed on the source document**. Two different authorities that
  quote the same provision are both kept; fifteen near-identical chunks from one
  advisory collapse to one.

This was added after a stolen-bike query returned a candidate pool dominated by
one advisory, crowding out the correct SOP entirely.

### 9.3 Reranking

A **cross-encoder**, `BAAI/bge-reranker-v2-m3`, scores each (query, passage)
pair jointly. Unlike bi-encoders, which embed query and document separately, a
cross-encoder sees both together and models their interaction — far more
accurate, and far too slow to run over a whole corpus, which is why it runs only
over the ~40 survivors.

`max_length=8192` (the model's full context, so 700-word chunks are not
truncated), `batch_size=8`, `normalize=True`.

### 9.4 The topic-anchor gate

The most-tuned part of the system, and the most fragile.

A high reranker score does not mean the passage answers the question. A privacy
chunk scored 0.224 on a phone-snatching query while the actual procedure went
unretrieved.

So after the first pass:

- Compute **anchor coverage**: what fraction of the query's focus tokens appear
  in a single 50-token window of the top hit, with light inflection stemming.
- **Fallback fires** if max reranker score < 0.15 **or** coverage < 0.5.
- **Anchor bypass** — a high score *without* the anchor — repeats the original
  topic once before appending generic procedure terms, so the generalised terms
  do not drown the anchor the winner lacked.
- The fallback pass **excludes candidates already scored**, so it explores
  rather than re-ranking the same set.
- Results merge: first pass preserved as the topical anchor, fallback fills the
  wider window. Scores from two different reranker queries are not comparable,
  so they are not mixed.

The gate applies **on every pass**, including retries. The retry query is built
from the **normalised topic query**, never from a previous expansion — otherwise
fallback scaffolding compounds and each retry drifts further from the question.

**This is honest about being heuristic.** `LOW_SCORE_FALLBACK_TERMS` is a fixed
phrase, and `PROCEDURE_ANCHOR_TERMS` is a hardcoded list. Both were tuned
against specific failures. They should be re-measured against a held-out golden
set and probably removed.

### 9.5 Query embedding performance

- **LRU cache** (256 entries) keyed on the normalised query **plus the model
  name and dimension** — two models produce vectors in different spaces, so the
  key must identify the space.
- **Micro-batching:** concurrent requests coalesce into one model pass through a
  10 ms window. Without it, three simultaneous Fast requests queue three passes
  and the last absorbs all preceding latency.
- **Separate semaphores and thread pools** for embedding and reranking, so a
  slow Deep rerank cannot head-of-line block a latency-sensitive query embedding.

### 9.6 The health checklist

`scripts/verify_retrieval_health.py` covers the failure modes that produce **no
error and no log line**. Current status against the live corpus: **12 passed, 0
failed, 0 blocked.**

| Check | What it catches |
|---|---|
| E-01 | Instruction prefix left over from a different model |
| E-02 | Normalisation/distance mismatch; sparse IDF modifier missing |
| E-03 | **Asymmetric query/document path** — measured cosine 1.000000 |
| E-05 | Silent 512-token truncation |
| E-06 | Cache key that survives a model change |
| E-07 | fp16 on CPU |
| E-08 | Inference silently on CPU |
| E-10/E-11 | Sparse from a second pass, tokenizer drift |
| E-12 | Unpinned Qdrant moving the RRF constant |
| E-17 | Point count vs manifest — 25,517 / 381 documents |
| E-18 | Empty chunk text |
| E-20 | Unindexed filter field forcing a scan |

---

## 10. The LLM boundary

`services/llm.py` — a thin, testable wrapper over self-hosted **Ollama**.

**Model:** `qwen3-14b-16k` (14.8B parameters, Q4_K_M, ~11 GB resident, 100% GPU
on an M5 Pro).

Every call:

```python
{"temperature": 0.0, "num_ctx": 16384, "num_predict": <per-call>, "think": False}
```

- **temperature 0.0** — legal answers should be reproducible.
- **`think: False`** — qwen3 is a reasoning model; its thinking trace would burn
  the token budget without reaching the user.
- **Concurrency bounded by a semaphore** (default 1), so a Deep run cannot
  starve every other session.

### 10.1 Structured output

Every stage that needs structure requests it against a **JSON Schema derived
from a Pydantic model**, so the model is grammar-constrained rather than asked
politely for JSON.

**Fallbacks, in order:**

1. Schema-constrained generation, up to 3 attempts.
2. If the server reports `failed to parse grammar`, drop to `format: "json"` and
   **inline the schema into the prompt** as instructions.
3. Parse failures are recorded per attempt with `parse_status` and the exception
   type, then retried.
4. On total failure, a `RuntimeError` carries `telemetry_metrics` so the failed
   attempts still appear in the trace.

**Node-level fallbacks:**

- `query_understanding` → regex `_fallback_intent`. The pipeline continues.
- `verification` → every claim marked `partial` with reason "Verifier
  unavailable". Since only `yes` is published, **a dead verifier abstains rather
  than publishing unverified text.** This is the important one: the failure mode
  is silence, not fabrication.
- `reasoning` → no fallback. There is no safe way to invent an answer.

### 10.2 Telemetry

Every call records prompt token count, context utilisation, time to first token,
tokens/second, `done_reason`, and Ollama's own load/prompt-eval/eval durations —
**including on the failure path**.

---

## 11. Verification: the core idea

This is the strongest part of the system.

### 11.1 The claim contract

`agents/reasoning_agent.py` does not ask for prose. It requires a structured
object:

```python
class _GroundedDraftClaim(BaseModel):
    category: Literal["direct_answer", "legal_basis", "application", "next_step", "limit"]
    claim: str = Field(min_length=1, max_length=600)
    source_chunk_ids: list[str] = Field(min_length=1, max_length=3)
```

At most **10 claims**, each at most **600 characters**, each citing **1–3 exact
chunk IDs**. Bounds are stated in the prompt *and* the schema — a schema-only cap
turns an over-long draft into a validation failure and a retry, costing more
than it saves.

Evidence is capped at **6,000 characters per chunk**. Each block carries
`CHUNK_ID`, `TITLE`, `ACT_NAME`, `SECTION`, `IS_CURRENT`, `IS_SUPERSEDED` and
page range, so the model can see currency, not just text.

**Chunk IDs are validated against the retrieved set in code.** A claim citing an
ID that was not retrieved is dropped before it can reach the verifier. The model
cannot invent a citation.

Rendered as: `[LEGAL_BASIS] <claim text> [SRC:gold-chunk-abc123]`

### 11.2 Independent verification

`agents/verification_agent.py` re-reads each claim against **only** its own
source's text.

- Claims are **grouped by source**, so a premise shared by five claims is sent
  once, not five times.
- Premise text is capped at **2,500 characters** per source. Uncapped, this
  prompt reached ~12,900 tokens — 79% of the context window and 40–50 seconds of
  prefill before the first output token.
- The verifier is told: verify each claim **only** against the premise in its own
  block; do not use another block.
- Verdict per claim: **`yes` / `partial` / `no`**.

Claim boundaries are found by splitting on `[SRC:]` markers rather than
sentences — legal text is full of abbreviations like "U.P.", "Cr.P.C." that
break sentence splitters.

Score = `(1.0·yes + 0.5·partial) / total_claims`. Below **0.5**, the graph
retries retrieval with a broadened query (max twice), then abstains.

---

## 12. Assembling the answer

`agents/response_generation.py` **rebuilds** the answer from verified claims. It
does not filter a draft.

Three rules:

1. **Only `yes` claims are published.** A `partial` verdict does not identify
   *which words* were supported, so publishing the compound claim would leak the
   unsupported part.
2. **A claim grounded in a superseded source is dropped**, even if the historical
   text entails it.
3. **Sentence-level filtering is not used**, because one paragraph can contain
   both supported and unsupported claims.

Survivors are grouped into citizen-worded sections:

| Category | Citizen heading |
|---|---|
| `direct_answer` | Direct answer |
| `legal_basis` | Why this is the legal position |
| `application` | How this applies to you |
| `next_step` | What you can do now (numbered) |
| `limit` | Important limits |

`[SRC:chunk-id]` markers are rewritten to `[Source N]`, and each becomes a
citation with title, source type, page range, court, Act, section, excerpt,
reranker score, verification status and currency status.

If no claim survives, the answer is `INSUFFICIENT_EVIDENCE` — an explicit
abstention, not a vague answer.

**Currency caveat:** if any cited source is not marked current, a "Source
currency" section is appended saying the current-law status is unverified. Given
`is_current` is false corpus-wide today, **this appears on every Deep answer**.

A disclaimer closes every answer: decision-support information, not a substitute
for a qualified professional.

### 12.1 A known structural weakness

The verifier applies **one entailment test to all five categories**, but three of
them cannot pass it by construction:

- `application` reasons about the user's facts, which are not in the premise.
- `next_step` proposes an action, which a passage describes rather than entails.
- `limit` asserts what the corpus **fails** to establish — the opposite of
  entailment.

So the sections most valuable to a citizen are the ones most likely to be
deleted. Accepted evidence shows this happening: run 09 shipped with
`has_legal_basis_heading: false`.

The fix is **per-category criteria, not a weaker gate**. It is deliberately not
implemented yet, because changing verification behaviour without a golden set to
measure against would be guessing.

---

## 13. Escalation and durable jobs

When Fast confidence < **0.6**, a weak answer is not published. Instead:

1. A `DEEP_REVIEW` job is enqueued with an idempotency key.
2. **The Fast brief is returned as provisional evidence**, labelled unverified,
   so the citizen has something to read during the wait.
3. The response carries `delivery_state: "searching_more_thoroughly"` and a
   `job_id`.

`services/job_worker.py`:

- Claims with `SELECT … FOR UPDATE SKIP LOCKED` — multiple workers are safe.
- **Cooperative cancellation:** the worker polls `cancel_requested` every 500 ms
  between stages, so a cancel takes effect mid-run.
- **Crash recovery:** `recover_interrupted_jobs` on startup and shutdown requeues
  anything left RUNNING.
- Bounded retry with attempt counts; sanitised error messages.
- Progress weighted by **measured** stage cost (reasoning 55%, verification 32%),
  credited on stage *completion*, with citizen-readable labels — "Checking every
  statement against its source", not "verification".

An SSE endpoint `GET /jobs/{id}/events` exists with `Last-Event-ID` resumption.
**The interface currently polls instead**; the stream is built but unconsumed.

---

## 14. Document upload

`routers/citizen_intake.py`. **Nothing uploaded is ever persisted or indexed.**

Bounds: 10 MiB, 20 pages, 20 megapixels, 12,000 characters extracted, 6 uploads
per minute, 2 concurrent extractions. Password-protected PDFs are rejected.

Extraction runs in a `TemporaryDirectory` removed on **every** path including
failure. Pages return to the client and are passed back per request.

`services/citizen_context.py` scores 320-word windows against the query and
packs the best into 9,000 characters.

**Prompt-injection defence** is layered:

- Document text is labelled in-prompt as untrusted facts, never instructions,
  never legal authority.
- Allegations are framed as conditional, not proven.
- A document ID can never be used as a legal `CHUNK_ID` — enforced in code, not
  only asked for.

---

## 15. The interface

Next.js 14 static export, also packaged as a Tauri desktop app.

**`lib/answer-presentation.ts`** restructures published text for display and
**must not add information the pipeline did not produce**. Two rules, both of
which were previously broken:

- **No verdict is inferred from prose.** Reading "Yes" off the front of a
  sentence and rendering it as a colour-coded legal finding promotes the model's
  wording to a conclusion. Removed.
- **Nothing verified is deleted.** The dedupe pass shared one `seen` set across
  sections, so a claim the verifier approved for two sections was silently
  dropped from the second — the renderer overriding the verifier. Each section
  now dedupes independently.

Abstention is read from `evidence_strength === "insufficient"`, not by matching
the prose of a backend constant.

Other behaviour: conversation history read from PostgreSQL (bodies on demand,
never in the sidebar payload); a working state with named stage, progress bar and
elapsed clock; a source inspector showing page range, verification status and
currency; feedback buttons wired to `POST /feedback`.

---

## 16. Where latency goes

Measured on an Apple M5 Pro, 24 GB, model 100% GPU-resident.

**Throughput:** prefill ~250–340 tok/s; decode 14.4 tok/s at short prompts
falling to 11.8 at 15k. The 4B tier does 30–45 tok/s.

**Accepted Deep run (295.7 s):**

| Stage | Time | Share |
|---|---:|---:|
| role_context | 0.1 ms | 0% |
| query_understanding | 18.6 s | 6.3% |
| retrieval | 20.1 s | 6.8% |
| **reasoning** | **162.6 s** | **55.0%** |
| **verification** | **94.4 s** | **31.9%** |
| response_generation | 1.4 ms | 0% |

**Deep is ~100% model-bound.** Every non-LLM stage costs under 2 ms. 1,688 output
tokens ≈ 165 s of decode; ~80 s of prefill. The lever is prompt and output size,
not device placement.

Applied: premise cap (~12.9k → ~6.5k tokens), reasoning bounds (20 claims of
1,400 chars → 10 of 600), conditional rewrite call. **Projected 120–138 s.**
Fast measures **70–95 ms**.

That projection has not been re-measured end to end. It is arithmetic from
measured token rates, not a timing.

---

## 17. Honest limitations

1. **The corpus cannot say what is current.** `current_status` is
   `"current/verify"` or similar for all 419 manifest rows, so `is_current` is
   false everywhere — deliberately, since an unverified status must not be
   asserted as current. Consequence: the currency caveat appears on every
   answer and therefore carries no information.
2. **Repealed law outnumbers current law five to one.** 5,387 chunks are the
   IPC, CrPC and Indian Evidence Act, repealed on 1 July 2024; their
   replacements total 1,026. Retrieval now names the repeal and prefers the
   provision in force by a three-place rank penalty, but the imbalance is a
   corpus problem and the preference is a mitigation, not a fix. The old codes
   are deliberately still retrievable: they govern conduct from before the
   repeal.
3. **The repeal label covers the Acts, not documents about them.** The rule
   matches a name that *begins* with a repealed code, so the 5,387 chunks of
   IPC/CrPC/Evidence Act text are labelled and an advisory citing section 498A
   is not. That negative direction is deliberate and tested — a circular that
   is still operative must not carry a "no longer in force" warning. The cost
   is visible: "can you help me now with the FIR procedure" cites *Amendment in
   Section 154 of the Code of Criminal Procedure* with no repeal marker, when
   FIR registration is now BNSS s.173. Widening the rule to any document
   mentioning a repealed Act would mislabel operative guidance, so this needs a
   document-type signal rather than a looser name match.
4. **Two known retrieval failures.** `search-of-place` and `phone-stolen` are
   missed by every configuration. Both relevance phrases exist verbatim in the
   corpus, so these are retrieval failures, not bad specifications.
   `phone-stolen` is a vocabulary gap — the citizen writes "my phone was
   stolen", the corpus writes "information relating to the commission of a
   cognizable offence".
5. **Two corpus gaps are answered rather than declined.**
   `consumer-complaint` and `posh-workplace`. Both contain a topical term the
   corpus holds in passing — "complaint" appears in 752 chunks — so the
   distinctive-term rule finds something to require and something that
   satisfies it.
6. **Verification uses one entailment criterion across five claim categories.**
   See [§12.1](#121-a-known-structural-weakness). Directly measured at 1.000
   with all five categories passing, so the predicted failure did not
   reproduce; the structural concern stands, the evidence for it does not.
7. **Sub-provision structural roles do not survive the chunk size.** 1,201
   chunks contain a proviso and none are labelled one, because the patterns
   are anchored at the start of a chunk and a 700-token chunk contains many
   provisos. The roles that do work are provision, definition and the
   parser-driven judgment roles.
8. **Deep is slow.** 78–85 s after the reranker and evidence caps. Honest
   progress reporting is still doing more for the experience than further
   optimisation would.
9. **The SSE stream is unused.** Built and tested; the client polls.
10. **"12 specialist agents" is prompt variation.** Five graph nodes are real.
11. **242 lines of retrieval code are unreachable.** The lexical-only path is
    never invoked, and it is the only thing that populates
    `lexical_distinctive_terms` — which the Fast lane read after it had stopped
    travelling that path, silently disabling the abstention gate. Fixed;
    the dead path remains.

### What changed, and what it was measured at

Against golden set v2 on the live collection, Fast lane (hybrid):

| | R@1 | R@5 | MRR | nDCG@10 | abstention | wrongly declined |
|---|---:|---:|---:|---:|---:|---:|
| before this work | 0.53* | 0.73* | 0.630* | 0.625* | 0.33 | not measured |
| now | 0.44 | 0.72 | 0.555 | 0.577 | 0.67 | 0.00 |

\* measured against golden set v1, which had 21 items rather than 24, credited
only the repealed Code of Criminal Procedure on two of them, and did not
measure false abstention. The recall columns are not directly comparable; the
abstention column is.

The number that moved most is the one that matters most here: the system now
declines twice as many questions it has no source for, and declines nothing it
can answer.

---

## Reference

**Code**

| Concern | File |
|---|---|
| Ingestion | `backend/app/ingestion/pipeline.py` |
| Extraction / OCR | `backend/app/ingestion/extract.py`, `ocr.py` |
| Structure / chunking | `backend/app/ingestion/structure.py`, `chunker.py` |
| Embedding | `backend/app/ingestion/embedder.py` |
| Qdrant | `backend/app/ingestion/qdrant_writer.py`, `init_qdrant.py` |
| Retrieval | `backend/app/services/retrieval.py` |
| Retrieval agent | `backend/app/agents/retrieval_agent.py` |
| Graph | `backend/app/agents/orchestrator.py` |
| Reasoning | `backend/app/agents/reasoning_agent.py` |
| Verification | `backend/app/agents/verification_agent.py` |
| Response | `backend/app/agents/response_generation.py` |
| Fast lane | `backend/app/services/fast_research.py` |
| Safety | `backend/app/services/citizen_safety.py` |
| Routing | `backend/app/services/adaptive_routing.py` |
| LLM | `backend/app/services/llm.py` |
| Jobs | `backend/app/services/job_worker.py` |
| Upload | `backend/app/routers/citizen_intake.py` |
| Presentation | `frontend/lib/answer-presentation.ts` |

**Health:** `python scripts/verify_retrieval_health.py --with-model`
**Throughput:** `python scripts/ollama_throughput_baseline.py`
**Tests:** 516 passing, 4 skipped (`RUN_INTEGRATION=1` with the compose stack
up; the skips are worker tests that require no other job worker on the same
database)
**Retrieval quality:** `python scripts/evaluate_retrieval.py`
**Evidence:** `docs/evidence/chunk-contract-v2-build.md`
