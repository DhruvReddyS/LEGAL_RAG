# 02 — Architecture

*How Corpusil works, component by component. Numbers in §2 measured
9 October 2026; the rest describes behaviour and is version-independent unless
it says otherwise.*

Everything is local. The only network calls are to `localhost`.

---

## 1. System shape

```
  Citizen / Police / Advocate / Admin
                │
                ▼
  Admission ─→ Safety screen ─→ Router ──fast──→ Hybrid retrieval → evidence brief
                                  │
                                  └──deep──→ LangGraph:
                                        role context
                                             → query understanding
                                             → retrieval
                                             → reasoning
                                             → verification
                                             → (retry, max 2)
                                             → response generation
```

| Layer | Technology |
|---|---|
| API | FastAPI, Python 3.12 |
| Relational store | PostgreSQL 16 (users, cases, chat, jobs, audit) |
| Vector store | Qdrant v1.18.2 (pinned — RRF is computed server-side) |
| Object store | MinIO (S3-compatible; corpus, case documents, generated files) |
| Embeddings | BAAI/bge-m3, 1024-d dense + learned sparse, one forward pass |
| Reranker | BAAI/bge-reranker-v2-m3 cross-encoder (**off by default**, §4.6) |
| Generation | Ollama, `qwen3-14b-16k` (Q4_K_M, 16,384 context) |
| Agent graph | LangGraph |
| Interface | Next.js 14 static export; Tauri desktop shell |

Everything is local. The only network calls are to `localhost`.

---

---

## 2. The corpus

| Property | Value |
|---|---|
| Manifest rows | 1,566 |
| Canonical documents (after de-duplication) | **1,563** |
| Pages | 55,382 |
| Indexed chunks | 49,684 serving (v4) · ~51,300 at v5's current progress |
| Collection | `global_legal_corpus_v4` serving, `_v5` building (name configurable, [04-OPERATIONS](04-OPERATIONS.md) §1.2) |

| | Documents |
|---|---|
| Acts | 802 |
| Rules | 361 |
| Official guidance, advisories, SOPs, manuals | 268 |
| **Judgments** | **93** (79 Supreme Court, 14 AP High Court) |
| Law Commission reports | 24 |

| Jurisdiction | Documents |
|---|---|
| India — Central | 1,260 |
| India — Andhra Pradesh | 288 |
| India — Telangana | 18 |

Material spans the Constitution, the 2023 Sanhitas and the codes they replaced,
Arms, Juvenile Justice, POCSO, IT and SC/ST legislation, Supreme Court and High
Court judgments, ministry advisories, SOPs and model manuals.

**Sources are curated, not crawled.** Every document is listed in
`data/legal_kb/metadata/canonical_documents.jsonl` with its origin URL, SHA-256
checksum, page count and a resolved type. Ingestion verifies the checksum before
touching the file, so a silently changed source fails rather than being indexed.
As of this writing every row carries a source URL, every row is marked verified
official, and no OCR work is outstanding.

### 2.1 De-duplication

Physical files reduce to canonical documents: the same Act arrives as multiple
scans, volumes and mirrors. `dedup.py` groups them by content and elects one
canonical member; the rest are recorded as its duplicates and are not embedded.
Without this, retrieval returns the same provision three times and crowds out
the rest of the answer.

### 2.2 What the corpus cannot yet support

Two gaps that decide which features are possible at all, carried here from the
retired `CORPUS_GAPS.md` because they belong beside the numbers above.

**93 judgments.** That is enough to answer a question *about* a well-known
case. It is not enough for precedent research, a citator, case comparison, or
checking an opponent's authorities — all of which need thousands. Four advocate
features are marked blocked in [01-PRODUCT](01-PRODUCT.md) §3 for this reason.

**Two states.** Central law plus Andhra Pradesh, with a little Telangana. A
citizen in any other state gets nothing state-specific on tenancy, land, police
rules or welfare, and the system correctly abstains rather than answering from
central law alone.

Closing either is acquisition work, not engineering — see CORP-01 and CORP-02
in [01-PRODUCT](01-PRODUCT.md) §3, and [06-PLAN](06-PLAN.md) Phase 2.

---

## 3. Ingestion, in detail

One pass, `backend/app/ingestion/pipeline.py`. Each document moves through
extraction → structure → chunking → enrichment → embedding → write, and every
stage writes to disk so the next run can resume.

### 3.1 Extraction (`extract.py`, `ocr.py`)

PDF text is pulled page by page. A page yielding fewer than **40 characters** is
treated as a scan rather than as an empty page, rendered at **300 DPI** and put
through Tesseract OCR.

The threshold matters: much of this corpus is scanned gazette material where a
page of dense legal text extracts as a handful of ligature artefacts. Setting it
too low indexes garbage; too high spends OCR time on genuinely blank pages.

Extracted text is cached at `processed/extracted_text/<canonical_id>.json`. This
cache is what makes re-chunking cheap — the `--rechunk` mode re-runs every later
stage without re-OCRing 381 documents.

### 3.2 Structure parsing (`structure.py`)

Flat page text is parsed into **structural units** — the natural divisions of the
document, not fixed-size blocks:

- **Statutes**: Part → Chapter → Section, with the heading path retained.
- **Judgments**: facts, issues, appellant arguments, respondent arguments, court
  analysis, ratio, final order.
- **Circulars and SOPs**: numbered paragraphs.

The judgment roles are what let an advocate ask for a *ratio* rather than a
paragraph that happens to mention the point.

### 3.3 Chunking (`chunker.py`)

Chunks are **700-token windows with 80-token overlap, taken within a structural
unit** — never across one. A window never spans two sections, so a chunk cannot
attribute one provision's text to another's number.

Each chunk carries:

| Field | Purpose |
|---|---|
| `chunk_id` | Content-addressed; changes when the text changes |
| `unit_id`, `unit_ordinal`, `unit_count` | Position within the parent unit — the hook for small-to-big retrieval |
| `structural_role` | provision / proviso / explanation / illustration / definition / schedule, or a judgment role |
| `embed_text` | What is actually embedded (§3.4) |
| `quality`, `quality_reason` | Whether it is indexed at all (§3.5) |
| `cited_provisions`, `cited_cases` | Deterministic cross-references (§3.6) |
| `act_name`, `section`, `page_start`, `page_end`, `heading_path` | Citation material |

### 3.4 `embed_text`: what gets embedded is not what gets quoted

The motivating failure: Article 14 of the Constitution is *"14. Equality before
law."* — four words. Nothing in that string tells an embedding model it is
constitutional law, so the query "explain the right to equality" retrieved the
Model Prison Manual instead.

So the vector is built from a prefixed form:

```
The Constitution of India · Part III — Fundamental Rights · Section 14 — 14. Equality before law.
```

Two rules keep this honest:

1. **The quoted text is never modified.** A citation shows the provision, not the
   prefix. `embed_text` exists only to be embedded.
2. **The prefix is capped at 180 characters.** A prefix longer than its own text
   makes every chunk of one Act look alike to the model, which destroys
   within-Act ranking — the opposite of the problem it was added to solve.

### 3.5 Quality classification (`enrichment.py`)

Roughly a fifth of raw chunks are furniture: page numbers, tables of contents,
registration numbers, bare headings, amendment footnotes. They are rejected at
chunking rather than filtered at query time, so they never occupy an embedding
or a candidate slot.

Rejection categories: `reference_number`, `page_artefact`, `table_of_contents`,
`amendment_footnote`, `bare_heading`, `too_short_no_operative_language`, `empty`.

**This is the riskiest component in ingestion**, because a false positive
silently deletes a provision a citizen might need. Two safeguards:

- An amendment footnote must show **three** signals — a footnote opening, an
  editorial marker (`ibid`, `w.e.f.`), and no operative language. "Omitted"
  alone appears in real provisions about omitted particulars.
- A section number is an escape hatch from the length rule, so a genuine
  one-line provision like `14. Repealed.` survives.

A rejected filter is recorded in `docs/evidence/` with why. One candidate rule —
rejecting garbled OCR by a wordlike-token ratio — was measured and **rejected**:
the band it would have deleted contained 436 provisions, including Articles 7
and 11 of the Constitution, which score low because the scan spaces its
em-dashes.

### 3.6 Citation extraction (`citations.py`)

Deterministic regex over each chunk, producing `act_key:number` references such
as `crpc:154` and normalised case citations. Roughly 28,000 edges across the
corpus; about half of all chunks carry a parseable reference.

The rule that makes it trustworthy: **an unqualified section number resolves to
the containing document's own Act, or stays unresolved.** Inside the CrPC,
"section 154" means CrPC s.154. With no such context, 1,379 references are kept
out of the graph rather than guessed at — a wrong edge is worse than a missing
one.

### 3.7 Embedding (`embedder.py`, `sparse.py`)

BGE-M3 produces the dense vector (1024-d, cosine) **and** the learned sparse
weights in **one forward pass** over the same text. Two passes would allow the
two representations to describe different strings, which is the classic
hybrid-search bug.

- fp16 on MPS/CUDA, fp32 on CPU.
- `max_length=8192`, set explicitly — the library default of 512 would silently
  truncate long provisions.
- Sparse vectors use Qdrant's **IDF modifier**, so term weights are corpus-aware.

Vectors are cached per document, so an interrupted run resumes without
re-embedding what it already did.

### 3.8 Writing and indexing (`qdrant_writer.py`, `init_qdrant.py`)

Points carry named vectors `dense` and `sparse`, plus a payload of everything
retrieval or citation needs. **Every field that any filter uses is indexed** —
verified by a check in `scripts/verify_retrieval_health.py`, because an
unindexed filter field turns a filtered query into a full scan.

### 3.9 Resumability

A 25,000-chunk build takes hours and will be interrupted. It has been, three
times — once by a sandbox permission error, twice by Docker stopping underneath
it.

- A per-collection checkpoint ledger records each completed document.
- `--resume` skips what is done; `--rechunk` re-runs parsing and chunking from
  cached extracted text without re-OCR.
- Two collections built in parallel keep **separate ledgers**, so a resume of one
  never skips documents because the other finished them.
- `scripts/run_rebuild.sh` supervises the whole thing: brings the stack up,
  resumes, repeats until the ledger is full.

---

---

## 4. Retrieval, in detail

`backend/app/services/retrieval.py`.

### 4.1 Hybrid search with server-side fusion

One query embedding produces both a dense and a sparse vector. Both are sent to
Qdrant in a single `query_points` call with two prefetch branches, and **Qdrant
fuses them with Reciprocal Rank Fusion server-side**.

Fusing in the database rather than in Python means one round trip instead of
two, and a fusion constant pinned by the database version rather than by our
code. The Qdrant version is pinned for exactly that reason.

Query embeddings are cached, keyed by **model name and dimension as well as the
query text** — otherwise a model change silently serves vectors from the old one.

### 4.2 The distinctive-term gate (abstention)

The mechanism that lets the system decline. For each query, term document
frequencies are counted across the corpus; the **rarest band** is required to
appear in a passage for that passage to be publishable.

A question about a landlord (37 chunks), noise (16), a consumer complaint (25)
or a Canadian visa (0) has a rare term that no passage satisfies, so nothing is
publishable and the system abstains.

Two corrections were needed before this worked on real phrasing:

- **Colloquial words are rare in a legal corpus.** Statutes say "any person",
  never "someone" — which appears in 90 chunks and became the required term for
  "when can police arrest someone without a warrant", rejecting every correct
  passage. Indefinite pronouns, light verbs and temporal deixis ("today",
  "currently") are dropped before the rule runs.
- **A rare inflection is not an absent topic.** "protections" appears in 35
  chunks and "protection" in thousands. Frequency is now taken across a term's
  spellings, with `-es` stripped only after a sibilant so "offences" does not
  become "offenc".

Measured effect: abstention accuracy 0.33 → 0.67 → **0.83**, with false
abstention driven from 0.28 to 0.00 at the time of that change.

### 4.3 Preferring the law in force

The corpus holds 5,387 chunks of repealed codes against 1,026 of their
replacements. Retrieval is volume-sensitive, so the repealed provision wins on
weight of material: per topic, "arrest without warrant" is 48 CrPC chunks to 23
BNSS.

A repealed provision is therefore demoted by a **rank penalty of three places**,
not a score multiplier — the ordering key is an RRF score in one lane and a
cross-encoder logit in the other, which are not on the same scale. The penalty
is deliberately mild: a repealed provision that is markedly the better match
keeps its place, because the old codes still govern conduct from before July
2024.

Measured: R@1 0.39 → 0.44, R@5 0.67 → 0.72, with abstention unchanged.

### 4.4 Case scoping

Private collections (`police_case_data`, `advocate_case_data`) hold one matter's
evidence. `case_ids` is applied only when non-empty — correct for the public
corpus, a disclosure for a private one, where an empty list means *every case*.

A private-corpus query with no case scope therefore **fails at the shared search
entry point** rather than returning someone else's evidence. This is structural,
not conventional, because the police and advocate modules will add call sites.

### 4.5 Supersession filtering

`exclude_superseded` excludes points where `is_superseded` is **explicitly
true** (`must_not`), not points where it is false (`must`). The field is
tri-state in practice — true, false, or absent on an index built before it
existed — and a positive match on `false` excluded the entire corpus.

### 4.6 Reranking is off, and why

A `bge-reranker-v2-m3` cross-encoder is wired in and **disabled by default**.

Measured twice, on two different golden sets:

| | R@1 | R@5 | R@20 | cite@5 | ms/query |
|---|---:|---:|---:|---:|---:|
| hybrid | 0.69 | 0.83 | 0.98 | 0.60 | **91** |
| reranked | **0.64** | 0.83 | 0.98 | 0.61 | **5,126** |

56× the cost, R@1 *falls*, recall does not move. Reranking is standard practice
and it does not help on this corpus — most likely because RRF over material this
homogeneous has already done the work the cross-encoder exists to do.

It remains a setting rather than a deletion, so the next corpus can be measured
with it rather than argued about.

**One coupling had to be handled.** `LOW_RERANKER_SCORE_FALLBACK_THRESHOLD` is
0.15, calibrated for cross-encoder output; a fused RRF score is about 0.016.
Switching reranking off without gating that comparison makes it true for every
query, silently sending every Deep search down the fallback path. The score half
of that rule now applies only when there is a cross-encoder score to judge.

---

### 4.7 Following citations to the law in force

The deepest retrieval defect in this project, and the one the other symptoms
sat on top of.

BNSS s.173 answers "how is an FIR registered?" and contains none of those
words -- it says "information relating to the commission of a cognizable
offence". Measured, the section does not appear in the top 100 for that
question, while its own text retrieves it at rank 1. The index is sound; the
gap is between how statutes are drafted and how people ask. The same holds
for s.482 on anticipatory bail and BSA s.26 on dying declarations.

Recall@5 read 0.927 throughout, because the golden set matches any passage
*containing* a phrase and a judgment quoting the provision satisfies that.
The metric was measuring "something relevant came back", never "the governing
provision came back".

What does rank for those questions is judgments, and they cite the repealed
codes -- CrPC s.154 for the FIR, s.438 for anticipatory bail -- because they
predate the Sanhitas. The concordance (§8.4) says where those provisions
went. So `citation_following.py` reads what the retrieved passages rely on,
follows it forward, and fetches the result. It is how a lawyer works: read
the commentary, follow it to the statute.

| question | before | after | cost |
|---|---:|---:|---:|
| how is an FIR registered | absent | rank 9 | 18 ms |
| anticipatory bail grounds | absent | rank 9 | 11 ms |
| dying declaration | absent | rank 9 | 6 ms |
| arrest without a warrant | rank 8 | rank 8 | 7 ms |
| "what did the Court hold in Puttaswamy" | — | adds nothing | 0 ms |

No model, one extra Qdrant call, and nothing invented: a provision the
concordance records as repealed without replacement yields nothing rather
than a nearest-numbered guess, and a citation to a code already in force is
not followed. Results are appended below everything retrieved on its merits,
because this is corroboration the sources pointed at, not a better match.

Two misses are honest and recorded. Default bail is not reached: the passages
cite CrPC ss.437 and 437A, which map to the BNSS bail sections rather than to
s.187, whose proviso creates the entitlement. Theft follows to BNS s.1,
because the retrieved judgments happen not to cite IPC ss.378 or 379.
Following citations reaches what the sources rely on, which is not always
what the question needs.

---

---

## 5. The two lanes

The router (`adaptive_routing.py`) picks a lane per question. Any signal of
complexity — a case-scoped matter, multiple issues, a request for analysis —
goes Deep. No signal goes Fast.

### 5.1 Fast — an evidence brief

`fast_research.py`. Retrieval and citation only: **no LLM call**. Returns in
**~90–230 ms**.

1. Normalise legal terms (one-edit correction against known acronyms; `pocos` →
   `POCSO`, and ambiguity refuses to correct).
2. Hybrid retrieval with RRF.
3. Apply the distinctive-term gate; abstain if nothing survives.
4. Emit numbered citations with page ranges, an evidence-strength rating, and any
   currency label.

It was lexical-only for a long time because the dense path measured 8,489 ms p95.
With warm models and the reranker input capped it is now ~91 ms, and the
relevance difference was not marginal: asked to explain Article 14, the lexical
lane returned the Model Prison Manual.

### 5.2 Deep — the agent graph

Full LangGraph pipeline with claim-level verification, **53.0 s p50** measured over 61 questions. Long-running
requests become durable jobs ([04-OPERATIONS](04-OPERATIONS.md) §1.4) with progress reporting.

---

---

## 6. The agent graph

`backend/app/agents/orchestrator.py`. Five real nodes.

| Node | Does |
|---|---|
| `role_context` | Loads the role profile — objective, response contract, safety boundary |
| `query_understanding` | Structured JSON: intent, entities, statutory references, filters |
| `retrieval` | Hybrid search across the public corpus and, if authorised, one case |
| `reasoning` | Emits **structured claims**, each naming the chunk IDs supporting it |
| `verification` | Grades every claim against its own sources (§7) |
| `response_generation` | Publishes only verified claims, with citations |

A failed verification can route back to retrieval, **at most twice**. The retry
guard sits at the retrieval branch rather than the verification branch, so a
repeated retrieval signature is detected before paying for another generation.

The "12 specialist agents" in the interface are **prompt variation over these
five nodes**, and this document says so rather than implying twelve processes.

Prompts are versioned by a **fingerprint of the source of the function that
builds them** (`prompt_registry.py`), so a version cannot go stale and a new
agent cannot ship unversioned — a test walks `app/` and asserts it.

---

---

## 7. Verification

The core safety property, and the thing that distinguishes this from a
summariser.

1. `reasoning` emits discrete claims. Each names the chunk IDs it rests on.
2. `verification` grades **each claim against its own source's premise text**,
   not against a general impression of the evidence.
3. `response_generation` publishes only claims graded `yes`.
4. A claim citing a chunk ID absent from the retrieved set is dropped, in code.
5. `publication.py` decides whether what survived is worth publishing at all.

### 7.1 The publication gate

Abstention was decided on `verification.score < 0.5`. That score is a *ratio* --
verified claims over all claims attempted -- so the gate punished thoroughness:
a broad question generates more claims, more are rejected, the ratio falls, and
the answer is discarded even though the absolute quantity of verified law is
higher than a narrow question's.

Measured on 61 questions, 6 September 2026: six of the nine wrongly refused
questions had verified claims that never reached the reader.
`child-needing-care` produced **ten** claims that passed verification, ran for
332 seconds across three passes, and printed "insufficient evidence".

The gate is now on absolute sufficiency:

| condition | outcome |
|---|---|
| no claim survived verification | abstain |
| every survivor is a caveat; none answers | abstain |
| under 20% of claims supported | abstain (fabrication guard) |
| otherwise | publish |

The floor is a fabrication guard, not a quality bar. Quality is carried by
per-section confidence (§7.2). The retry branch applies the same test, so the
graph cannot retry a result it would have published.

This is not a relaxation of verification. Each claim is still judged against its
own chunk and only `yes` claims are published; what changed is that rejected
siblings no longer suppress the survivors, which they were never evidence
against.

### 7.2 Per-section confidence (`section_confidence.py`)

One number for a whole answer hides the case that matters: an answer can state
the governing provision from the Sanhita and then draw its practical steps from
a single circular. Each published section is graded from what its claims cite --
document type, currency, source count -- with no model involved.

Three rules, each because the alternative flatters a weak section:

- one source is never **strong**, however good it is;
- guidance alone is never **strong**: three circulars agreeing establish what an
  administrator believed the law to be, not what it is;
- an unverified current-law status caps the section at **moderate**.

Authority tiers come from the stored `document_type`, falling back to
`source_type` for points indexed before the classifier existed -- the v2 index
carries no `document_type` at all, so on that corpus the fallback is the only
signal there is.

Bounds that keep it tractable: premise text capped at 2,500 characters, evidence
at 3,500, ten claims of 600 characters each. A verifier that returns fewer
verdicts than claims is re-asked **only for the outstanding indexes**.

**Unadjudicated claims are excluded from the denominator, not scored as
failures.** Recording them as "no" produced verification scores of exactly 3/14
and 3/10 — the appearance of a quality problem that was really a bookkeeping
one. Fixing it moved the score to 0.923.

---

---

## 8. Currency and repeal

### 8.1 The resolver (`currency.py`)

Deterministic. Returns one of three answers for any cited authority:

| Status | Meaning |
|---|---|
| `in_force` | Curated as current |
| `superseded` | Replaced, with the successor named |
| `unverified` | No curated status — labelled as such, **never assumed current** |

Resolution order: curated table → repeal table → the stored ingestion flag (only
when explicitly `true`) → unverified.

This replaced seven separate reads of `payload["is_superseded"] is True`. That
field was written by ingestion but added after the index was built, so all
25,517 points of that earlier build held `None` and every one of those guards evaluated false forever
while reading as protective.

### 8.2 Failing closed, in three cases not two

| Case | May ground a published claim |
|---|---|
| Superseded, no savings | **No.** A model manual replaced by a later edition governs no period at all |
| Superseded, saves prior conduct | **Yes, with the repeal stated.** An offence committed on 30 June 2024 is tried under the Penal Code |
| Unverified | **Yes, with the label.** The corpus cannot verify most of itself |

Collapsing the first two produces a wrong answer rather than no answer.

Curated coverage: 18 authorities, 9,770 chunks. After migration: 6,131 in force,
3,821 superseded, 15,181 unverified.

### 8.3 Two labels (`repeal_labels.py`)

| Label | Applies to |
|---|---|
| **A** — no longer in force | The repealed Act itself |
| **B** — concerns a repealed provision | Guidance, manuals and judgments *about* a provision that moved |

Label B exists because loosening Label A's name match would put "no longer in
force" on an advisory about s.498A, which still binds. It uses two signals that
already existed: `source_type` distinguishes the authority (ACT, RULE,
NOTIFICATION, ORDER) from material about it, and the citation extractor supplies
the references.

### 8.4 Section mapper (`section_mapping.py`)

Bidirectional lookup over IPC/BNS, CrPC/BNSS and IEA/BSA. **2,596 pairs, built
from the National Crime Records Bureau's published correspondence tables** by
`scripts/build_section_mapping.py`. NCRB is a bureau of the Ministry of Home
Affairs and publishes the concordance as HTML; the MHA's own PDF is a two-page
scan, and OCR on a dense table of numbers fails silently, which is worse than
having no table.

This replaced 54 model-authored pairs. The audit is the reason the replacement
mattered: **51 agreed, 2 were the new parser's fault, and 1 was wrong.** The
wrong one was IPC s.124A → BNS s.152 — sedition. That equivalence is repeated
across commentary and the press, and it is the pair a reviewer would approve
fastest. The official table records s.124A as **deleted**: not carried forward,
no successor, and BNS s.152 is a separate offence with different elements.

Three properties the official data forced into the code:

- **One provision often replaces many.** BNS s.179 stands in for eleven IPC
  sections. The reverse direction used to be inverted from the forward pair;
  inverting one-to-many invents a precision the Act never had, so both
  directions are now read from the source and lookups return tuples.
- **`not_re_enacted` is distinct from `no_mapping_known`.** "The new code
  dropped this" and "this table has not heard of it" are different answers, and
  merging them turns a finding into a gap.
- **A citation without a sub-section matches all of them.** The BNSS concordance
  is printed at sub-section level, so exact matching alone returned nothing for
  "BNSS s.35" and "BNSS s.173" — the arrest power and the FIR provision.

633 pairs (24%) carry `ingredients_changed`, taken from the source table's own
`(Change)` marker rather than from judgement.

> **Status: `official_source`.** Every consumer surfaces it.

### 8.5 Authority check (`authority_check.py`)

The advocate-facing use of the concordance: paste a draft, and every provision
it cites is checked against the codes in force. Deterministic — citations come
from the ingestion pipeline's own parser, and no model reads the draft, because
a model's failure mode here is to confidently renumber a provision that was
repealed without replacement.

Findings are ordered by what the drafter must do: `not_re_enacted` first
(cannot be fixed by substituting a number), then `elements_changed` (needs
judgement), then `renumbered` (find-and-replace). Citations to acts outside the
concordance are listed as `not_checked` rather than omitted — an absent row
reads as "checked and fine".

---

---

## 9. Safety screening

`citizen_safety.py`, before retrieval.

**Emergency** — surfaces the relevant helpline immediately rather than a legal
answer: immediate violence, child at risk, self-harm, offence in progress,
financial fraud in progress. Numbers: 112, 1091, 1098, 14416, 1930, NALSA 15100.

**Refusal** — requests to evade law, fabricate evidence or identify a private
individual.

The hard part is **not over-firing**. Three false positives were found by running
real questions rather than by reading the patterns:

- "What is the punishment for theft under the law in force **today**?" was a
  child-protection emergency — an ungrouped alternation made the bare word
  "today" match.
- "can you **help me now** with the FIR procedure" was immediate violence.
- "What is the punishment for **being kidnapped**?" was an offence in progress.

Each replaced a legal answer with a helpline. A test now asserts the *rule* — no
top-level pattern branch may be a bare short phrase — with `self_harm` explicitly
exempt, because there the harms are asymmetric and narrowing it to satisfy a lint
would be weakening a safety check.

---

---

## 10. Security model

### 10.1 Authentication and authorisation

JWT access and refresh tokens; refresh tokens are single-use with reuse
detection and a `jti` denylist. Permissions are database-driven
(role → permission), not hardcoded.

| Role | Corpus read | Owns cases | Manages case documents |
|---|:---:|:---:|:---:|
| citizen | yes | no | no |
| police | yes | yes | yes |
| advocate | yes | yes | yes |
| admin | yes | yes | yes |

### 10.2 Case isolation

The boundary the police and advocate modules are built on.

- A case is reachable by its owner; an administrator may reach a **named**
  matter, because naming it is what makes it authorised and auditable.
- A **general** search never reaches a private corpus for a matter the caller
  does not own — including for administrators. Removing that exemption fixed a
  live disclosure in which one admin query enumerated every case in the database.
- A stranger requesting another user's case gets **404, not 403**: a 403 would
  confirm the matter exists.
- Evidence is stamped with `case_id`, `document_id`, `uploaded_by` and
  `corpus_scope` at index time.

### 10.3 The red-team suite

36 tests over `{citizen, police, police_two, advocate, advocate_two, admin}` ×
`{general, named matter}` × `{own, sibling in the same collection, other role,
none}`, against **real Qdrant with real embeddings**. A fake retrieval service
would prove the authorisation decision is right while leaving a wrong filter
undetected — and those are different bugs.

Assertions are made at two levels: what came back (a leak that reached the
caller) and what was asked (a private collection in the query targets at all).

Every guard is verified by removal. That process found a hole in the suite
itself: deleting the Qdrant `case_id` filter was caught by one test, because the
police and advocate cases lived in different collections and the collection
boundary was doing the tenant filter's job. Adding same-role siblings took it
from 1 detector to 10.

### 10.4 Privacy

A citizen's question is often the most sensitive thing they will type. It travels
in a request body, never a URL. The access log records request id, method, path,
status and duration — nothing else. Dependency-outage handlers log an error type,
not the exception message, which can carry connection details. All four
properties are asserted by tests.

---

---

## 11. Module map

**Ingestion** — `backend/app/ingestion/`

| File | Concern |
|---|---|
| `pipeline.py` | Orchestration, checkpointing, resume, `--rechunk` |
| `extract.py`, `ocr.py` | PDF text, scan detection, Tesseract |
| `structure.py` | Statute and judgment structure |
| `chunker.py` | Token windows within units; the chunk contract |
| `enrichment.py` | Quality classification, structural role, `embed_text` |
| `citations.py` | Deterministic cross-references |
| `supersession.py` | Repeal table |
| `embedder.py`, `sparse.py` | BGE-M3 dense and sparse |
| `qdrant_writer.py`, `init_qdrant.py` | Payload and indexes |
| `dedup.py`, `metadata.py`, `validate.py` | Canonicalisation and integrity |

**Retrieval and services** — `backend/app/services/`

| File | Concern |
|---|---|
| `retrieval.py` | Hybrid search, RRF, filters, case-scope guard, rank preference |
| `fast_research.py` | The Fast lane and its abstention gate |
| `adaptive_routing.py` | Fast/Deep selection, including backreference escalation |
| `currency.py` | Three-state currency resolution |
| `repeal_labels.py`, `section_mapping.py` | Labels A and B; the concordance |
| `citation_status.py` | One label builder for every lane |
| `section_confidence.py` | Per-section grounding: authority tier, source count, currency |
| `citation_following.py` | Reaching the provision in force via what the corpus cites |
| `authority_check.py` | Checks a draft's citations against the codes in force |
| `investigation_timeline.py` | Nine BNSS statutory deadlines, computed not recalled |
| `investigation_compliance.py` | BNSS requirements per police action, three-state |
| `citizen_safety.py` | Emergency and refusal screening |
| `llm.py`, `generation.py` | Ollama client, metrics, 503 handling |
| `job_worker.py`, `jobs.py` | Durable jobs |
| `auth.py`, `token_revocation.py` | Tokens and reuse detection |
| `case_documents.py`, `storage.py` | Private evidence indexing |
| `health.py` | Liveness, readiness, boot assertions |

**Agents** — `backend/app/agents/`

`orchestrator.py` · `query_understanding.py` · `retrieval_agent.py` ·
`reasoning_agent.py` · `verification_agent.py` · `publication.py` ·
`response_generation.py` · `role_profiles.py` · `drafting_agent.py` ·
`defence_strategy_agent.py` · `prompt_registry.py`

**Evaluation** — `backend/app/evaluation/`

`answer_quality.py` (five answer metrics) · `golden_set.py`

**Scripts** — `scripts/`

| Script | Use |
|---|---|
| `evaluate_retrieval.py` | Golden-set metrics and the four-way ablation |
| `check_quality_gate.py` | Regression gate against the recorded baseline |
| `measure_baseline.py` | Throughput, TTFT, per-stage timings, memory validity |
| `verify_retrieval_health.py` | 20 silent-failure checks over config and index |
| `migrate_currency_payload.py` | Resumable currency backfill |
| `run_rebuild.sh` | Supervised corpus rebuild |

**Data** — `data/legal_kb/`

`metadata/canonical_documents.jsonl` · `metadata/currency_status.json` ·
`metadata/section_mapping.json` · `evaluation/golden_set_v3.json` ·
`processed/` · `cache/` · `logs/`
