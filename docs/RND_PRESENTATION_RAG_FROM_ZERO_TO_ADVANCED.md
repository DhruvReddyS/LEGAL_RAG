# Corpusil RAG: From Zero Knowledge to the Complete Working System

This guide is written for a presenter who is starting from the basics. It first
builds the vocabulary, then explains the complete pipeline implemented in this
repository, and finally gives a presentation structure and viva questions.

> One-sentence project definition
>
> Corpusil is a local, multi-role legal decision-support system that retrieves
> relevant Indian legal material using hybrid search, generates an answer from
> that evidence, verifies every proposed claim against its cited passage, and
> abstains when the evidence is inadequate.

---

## 1. Start with the problem, not the technology

Suppose a user asks:

> Can police arrest a person without a warrant, and what safeguards apply?

A normal search engine can return links. A general Large Language Model (LLM)
can write a fluent answer. Neither result is automatically safe for legal use:

- a search result still leaves the user to locate the relevant passage;
- an LLM may answer from incomplete training memory;
- it may invent a section or judgment;
- it may use repealed law as though it were current;
- it may sound certain even when the required law is absent;
- different users need different forms of the same information;
- private police or advocate case material must not leak between matters.

The project therefore does not ask the LLM to answer from memory. It first
locates evidence from a controlled legal corpus, then permits only verified
claims to reach the user.

This is the reason for using RAG.

---

## 2. Essential vocabulary from the beginning

### 2.1 Artificial intelligence, machine learning and an LLM

- **Artificial intelligence (AI)** is the broad field of making machines perform
  tasks that normally require human intelligence.
- **Machine learning (ML)** is a part of AI in which a model learns patterns from
  data instead of being given a rule for every possible case.
- A **Large Language Model (LLM)** learns statistical patterns in language and
  predicts useful sequences of text. In this project, the local generation model
  is served through Ollama.

An LLM is good at language generation and reasoning-shaped tasks, but it is not
a legal database. It can produce a convincing sentence without possessing an
authoritative source for that sentence.

### 2.2 Token

A **token** is a small unit of text processed by a language model. It may be a
word, part of a word, punctuation, or a number. Context-window and chunk sizes
are commonly measured in tokens.

### 2.3 Corpus

A **corpus** is the controlled collection of source material available to the
system. Here it includes legal texts such as Acts, rules, judgments, circulars,
SOPs and manuals.

The corpus is not identical to every PDF that has been downloaded:

- `data/source_materials/` contains archival material and candidate imports;
- `data/legal_kb/` is the active, reviewed knowledge-base source;
- a candidate affects answers only after review, promotion and indexing.

This distinction prevents an unreviewed download from silently becoming legal
authority in an answer.

### 2.4 Knowledge base

A **knowledge base** is the organized, searchable form of the corpus. It includes
more than the source files. It also contains extracted text, chunks, metadata,
vectors and stable identifiers.

### 2.5 Chunk

An entire Act or judgment is too large and too imprecise to retrieve as one
object. It is split into smaller passages called **chunks**.

If a 200-page Act were stored as one vector, a query about one section would be
compared with the meaning of the entire Act. A focused chunk lets the search
engine retrieve the exact provision and lets the interface cite exact pages.

### 2.6 Embedding and vector

An **embedding model** converts text into numbers that represent meaning.

Simplified example:

```text
"arrest without warrant" -> [0.12, -0.48, 0.77, ...]
```

That list is a **vector**. Real project vectors have 1,024 dense dimensions.
Texts with related meanings tend to have vectors close to one another.

The embedding model does not generate the answer. It creates the numerical
representation used to find evidence.

### 2.7 Vector database

A **vector database** stores vectors and efficiently finds nearby vectors. This
project uses **Qdrant**. Each Qdrant point holds:

1. a stable point ID;
2. a dense vector;
3. a sparse vector;
4. the original legal passage;
5. metadata such as Act, section, court, pages and currency status.

### 2.8 Retrieval

**Retrieval** means selecting the most relevant evidence for a question. It is
not answer generation. A retriever returns passages; a generator uses those
passages to compose an answer.

### 2.9 Prompt

A **prompt** is the instruction and context sent to the LLM. In RAG, it normally
contains the user question, role instructions, retrieved evidence and output
rules.

### 2.10 Hallucination

A **hallucination** is content generated without adequate factual support. In a
legal system this may be an invented section, remedy, deadline or precedent.

### 2.11 Citation

A **citation** in this project is not merely text written by the LLM. It is a
structured object connected to a retrieved `chunk_id`, including its title,
Act/court, section, pages, excerpt, currency status and verification status.

### 2.12 RAG

**Retrieval-Augmented Generation** has two core stages:

```text
Question -> retrieve evidence -> generate an answer using that evidence
```

- **Retrieval** supplies external, inspectable knowledge.
- **Augmented** means that knowledge is added to the model's prompt.
- **Generation** turns it into a readable answer.

The project's full flow adds important stages before and after these two.

---

## 3. What type of RAG this project uses

The most accurate label is:

> Domain-specific, multi-role, agentic hybrid RAG with claim-level verification,
> corrective retry and abstention.

Each word has a reason:

| Term | Meaning in this project |
|---|---|
| Domain-specific | Built for Indian legal research, not general web knowledge |
| Hybrid | Combines semantic dense retrieval and lexical sparse retrieval |
| Agentic | A bounded LangGraph workflow assigns specialized stages and decisions |
| Multi-role | Citizen, police, advocate and admin receive different objectives and response forms |
| Verified | Proposed claims are checked against their own retrieved passages |
| Corrective | Weak evidence can trigger a broadened retrieval pass, at most twice |
| Abstaining | The system can say that the corpus lacks adequate evidence |

It is **not naive RAG**, because it does more than vector search followed by one
LLM call. It is **not GraphRAG**, because a knowledge graph is not the main
retrieval mechanism. The project does extract deterministic citation links and
follow some provisions, but retrieval is fundamentally Qdrant hybrid search.

---

## 4. Complete architecture at a glance

```text
OFFLINE / INGESTION PATH

Official legal sources
        |
        v
Candidate downloads and validation
        |
        v
Promotion into data/legal_kb + canonical manifest
        |
        v
Checksum -> PDF extraction/OCR -> legal structure parsing
        |
        v
Structure-aware chunks -> quality/citation/currency enrichment
        |
        v
BGE-M3 dense + sparse embeddings
        |
        v
Qdrant vectors + passage + metadata


ONLINE / QUESTION-ANSWERING PATH

User question
        |
        v
Authentication/admission -> safety screen -> fast/deep router
        |
        +---------------- FAST ----------------+
        | hybrid retrieval -> relevance gate   |
        | -> evidence brief + citations        |
        +--------------------------------------+
        |
        +---------------- DEEP ------------------------------+
          role context -> query understanding -> retrieval
          -> grounded reasoning -> claim verification
          -> optional retry (maximum 2) -> response generation
          -> cited answer or abstention
```

### Technology map

| Responsibility | Technology |
|---|---|
| User interface | Next.js, wrapped as a Tauri desktop application |
| API and business logic | FastAPI / Python |
| Users, sessions, cases, jobs and audit data | PostgreSQL |
| Legal vector search | Qdrant |
| Source/object files | S3-compatible storage such as MinIO |
| Dense and sparse embeddings | BAAI/BGE-M3 |
| Optional cross-encoder reranker | BAAI/bge-reranker-v2-m3, disabled by default |
| Local answer generation | Ollama with `qwen3-14b-16k` |
| Deep workflow orchestration | LangGraph |

The important database distinction is:

- PostgreSQL stores application relationships and transactions.
- Qdrant stores search vectors plus retrieval metadata.
- Object storage/filesystem stores original files and processing artifacts.

One database is not forced to do every job.

---

## 5. Phase A: data collection and source governance

### 5.1 Why collection quality matters

RAG quality is bounded by corpus quality:

```text
Wrong or missing source -> wrong or missing retrieval -> no trustworthy answer
```

Making the LLM larger cannot recover a statute that was never indexed.

### 5.2 Source-selection policy

The intended priority is:

1. official government and court sources;
2. primary law: Constitution, Acts, rules and authoritative judgments;
3. official circulars, notifications, SOPs and manuals;
4. secondary material only when its licensing and role are explicit.

For every source, the collection process should establish:

- identity: what legal instrument is it?
- authority: who issued it?
- jurisdiction: central, Andhra Pradesh, Telangana, etc.?
- language: is it English for the present corpus requirement?
- document type: Act, rule, judgment, circular, guidance or other?
- temporal status: current, repealed, superseded, or still requiring review?
- provenance: what official URL supplied it?
- integrity: is it a valid, readable PDF?
- duplication: is the same content already present?
- licensing/access: may it be retained and used?

### 5.3 Candidate versus promoted data

A download is first a **candidate**. It should be promoted only after the above
checks. Promotion updates the canonical corpus manifest and places the accepted
source under `data/legal_kb/`.

This is a data-governance gate:

```text
Downloaded != trusted
Trusted != indexed
Indexed != automatically sufficient for every question
```

### 5.4 Manifest

The canonical manifest is the inventory and provenance record. A document row
includes fields such as:

- `document_id` and `canonical_document_id`;
- title and local path;
- source type and official URL;
- jurisdiction, court, Act and section;
- decision date/year;
- current status and supersession information;
- language;
- SHA-256 checksum, file size and page count;
- whether the source is officially verified;
- quality status.

The manifest makes corpus construction reproducible. The system does not have
to guess later where a PDF came from or whether it was the reviewed file.

### 5.5 Checksum and de-duplication

**SHA-256** creates a content fingerprint. If two files have the same fingerprint,
they contain the same bytes. The pipeline verifies each document against its
manifest checksum before ingestion.

Physical copies can map to one canonical document. Only one member per
`canonical_document_id` is ingested. Otherwise the same provision could occupy
several top result positions and reduce evidence diversity.

---

## 6. Phase B: ingestion—turning PDFs into a searchable knowledge base

Ingestion is an offline ETL-style pipeline:

- **Extract** content from source files.
- **Transform** it into structured, enriched chunks and vectors.
- **Load** those points into Qdrant.

The implementation is resumable and has checkpoints so an interruption does
not require starting the whole corpus again.

### 6.1 Step 1: integrity verification

Before processing, the pipeline recomputes the file checksum and compares it
with the manifest. A changed or mismatched file fails instead of being silently
indexed under the wrong provenance.

### 6.2 Step 2: PDF text extraction

PyMuPDF extracts text page by page. Page numbers are retained because citation
quality depends on them.

Indian bare Acts commonly print marginal notes in a left column. A naive text
extractor can weave the marginal-note words into every body line. The project
uses page geometry to separate that column and restore readable statutory text.

### 6.3 Step 3: OCR fallback

If native extraction returns fewer than 40 characters for a page, the page is
treated as a probable scan. It is rendered at 300 DPI and sent through
Tesseract OCR. OCR is used only when it provides more useful text than the
native extraction.

**OCR** means Optical Character Recognition: reading text from pixels in an
image. It is necessary for scanned judgments and Gazette material, but it can
introduce errors, which is why quality controls remain important.

### 6.4 Step 4: legal structure parsing

The extracted text is not split blindly every N characters. It is first parsed
into natural legal units:

- statute: Part -> Chapter -> Section;
- judgment: facts, issues, arguments, analysis, ratio and order;
- circular/SOP: headings and numbered paragraphs.

This is called **structure-aware processing**. A section boundary has legal
meaning. Preserving it improves retrieval and avoids joining text from two
different provisions into one citation.

### 6.5 Step 5: structure-aware chunking

Each legal unit is divided only if it exceeds the maximum size. The current
contract uses windows of up to 700 whitespace tokens with 80-token overlap.

Why overlap? A relevant sentence may sit at the boundary between two windows.
Overlap repeats a small amount of context so the meaning is not cut abruptly.

Why not enormous chunks?

- their meaning becomes diluted;
- they consume more LLM context;
- citations become less precise;
- reranking becomes slower.

Why not tiny chunks?

- conditions and exceptions get separated;
- a provision loses context;
- the answer model sees fragments rather than a complete rule.

Each chunk retains its parent `unit_id`, ordinal position and unit count. This
supports a future or selective **small-to-big** pattern: match a precise child
passage but recover its larger parent provision where necessary.

### 6.6 Step 6: enrichment

Every chunk receives search and citation metadata:

- stable `chunk_id`;
- document and canonical IDs;
- title and source type;
- Act, section and subsection;
- court, jurisdiction and decision date;
- page range and heading path;
- structural role such as provision, proviso, ratio or order;
- references to cited provisions and cases;
- current/superseded/repealed information;
- official-verification and quality fields.

The chunker also classifies furniture/noise. Rejected material is not embedded,
so a masthead or punctuation fragment cannot waste a candidate position.

### 6.7 `text` versus `embed_text`

This is a particularly strong design choice.

- `text` is the verbatim passage displayed and verified.
- `embed_text` adds retrieval context such as Act name, heading path and section.

Example:

```text
Verbatim text:
14. Equality before law.

Embedding text:
The Constitution of India · Part III — Fundamental Rights ·
Section 14 · 14. Equality before law.
```

The richer form helps semantic search, while the unmodified form keeps the
citation honest. Search representation and quoted evidence serve different
purposes and therefore are stored separately.

### 6.8 Step 7: dense and sparse embeddings

BGE-M3 encodes each `embed_text` in one model pass and produces:

1. a **dense vector**: 1,024 floating-point values representing overall meaning;
2. a **learned sparse vector**: token IDs and weights representing important
   lexical features.

Dense representation is strong for paraphrases:

```text
"taken into custody without prior court permission"
              approximately means
"arrest without warrant"
```

Sparse representation is strong for exact legal anchors:

```text
BNSS 35, Article 21, POCSO, a case name, a technical phrase
```

Using both reduces the weaknesses of using either alone.

### 6.9 Step 8: Qdrant write

For each chunk, Qdrant stores a point containing named dense and sparse vectors
plus the passage payload. Dense similarity uses cosine distance. The sparse
index uses IDF weighting so rare terms generally carry more discrimination than
common terms.

The system upserts a complete replacement before deleting stale points from an
older chunking version. This reduces the risk of leaving a document partially
indexed during replacement.

### 6.10 Step 9: caching, checkpoints and validation

- extracted text is cached so re-chunking need not repeat OCR;
- embedding batches are cached so interrupted work can resume;
- a collection-specific checkpoint records completed and failed documents;
- per-document locks prevent two workers from processing the same document;
- vector, payload, page-range and expected-chunk validation checks the result.

Collection-specific caches matter because a new chunking contract may preserve
a chunk ID while changing the text represented by its vector. Reusing the old
vector would make the index internally inconsistent.

---

## 7. What exactly is stored where

### Original/candidate files

- candidate downloads: `data/source_materials/`;
- promoted source corpus and processing artifacts: `data/legal_kb/`;
- deployed object storage can use MinIO/S3-compatible buckets.

### Qdrant

Qdrant holds search-time data:

- dense vector;
- sparse vector;
- verbatim chunk text;
- citation and legal metadata;
- corpus tier;
- case scope where relevant.

### PostgreSQL

PostgreSQL holds application data:

- users and authorization;
- cases and chat sessions;
- messages and returned citation objects;
- durable deep-review jobs;
- feedback and audit logs.

### Public and private collections

- global legal material uses the configured global collection;
- police case data uses `police_case_data`;
- advocate case data uses `advocate_case_data`.

Private retrieval requires both an allowed role and the matching `case_id`
filter. Public law and private matter evidence may be searched together for an
authorized request, but their boundaries remain explicit.

---

## 8. Phase C: what happens when a user asks a question

### 8.1 Request admission and safety screening

The API first authenticates the user and validates access. Safety screening
happens before retrieval or generation. Emergency or disallowed situations can
be handled without pretending they are ordinary research questions.

### 8.2 Adaptive routing: Fast or Deep

The user can explicitly choose a lane, or select automatic routing.

Automatic routing uses deterministic signals—not another LLM call. It chooses
Deep Review for signals such as:

- a case-scoped matter;
- a follow-up that refers to earlier conversation;
- defence strategy or case analysis;
- evidence contradictions or chain of custody;
- comparative arguments;
- legal drafting;
- applying or distinguishing precedent;
- a long multi-fact query;
- multiple questions or multiple provisions.

A focused authority lookup normally uses Fast mode.

If Fast mode finds only low-confidence evidence, the system can enqueue a Deep
Review while still showing the provisional evidence brief.

---

## 9. Phase D: hybrid retrieval in depth

### 9.1 Query normalization

Legal term normalization corrects known terminology variants or mistakes before
search. In Deep mode, query understanding also resolves conversational references
and extracts entities such as Acts and sections. A simple self-contained query
can skip that LLM call and take a deterministic path.

### 9.2 Query embedding

The same BGE-M3 family used for documents encodes the normalized question into
a dense vector and sparse weights. Document and query representations must be
compatible for meaningful similarity.

Repeated query embeddings are cached. Near-simultaneous queries can be batched
to reduce model contention.

### 9.3 Metadata filtering

Before or during vector search, Qdrant filters can constrain:

- source type;
- court and jurisdiction;
- Act and section;
- date/year range;
- current-only or exclude-known-superseded;
- corpus tier;
- private `case_id`.

Filtering is not the same as ranking. A filter defines what is eligible; ranking
orders eligible candidates by relevance.

### 9.4 Parallel dense and sparse search

Qdrant performs:

```text
dense query  -> semantic ranking
sparse query -> lexical ranking
```

Dense retrieval may understand that "police custody without court order" relates
to warrantless arrest. Sparse retrieval protects exact terms like `BNSS`, a
section number or a case name.

### 9.5 Reciprocal Rank Fusion (RRF)

The two rankings have incomparable raw scores. RRF combines their **positions**
rather than mixing raw similarity values.

Conceptually:

```text
RRF score(document) = sum over result lists of 1 / (k + rank)
```

A passage ranked highly in both lists receives a strong combined score. A
passage missed by one method can still survive if the other ranks it well.

In this project, RRF runs server-side inside the pinned Qdrant version. The exact
`k` constant is controlled by Qdrant rather than application code.

### 9.6 Near-duplicate removal and diversity

Highly similar chunks from the same source are collapsed before expensive
reranking or final selection. Similar text from different authorities is kept,
because independent legal sources may legitimately corroborate a proposition.

### 9.7 Optional cross-encoder reranking

A **bi-encoder** embeds the query and documents separately; this makes initial
retrieval efficient. A **cross-encoder** reads each query-passage pair together;
it can judge relevance more precisely but is much slower.

The project contains `BAAI/bge-reranker-v2-m3`, but cross-encoder reranking is
disabled by default. Current deployment uses dense+sparse RRF as the normal
ranking signal. This is a measured latency/quality decision, not a missing
feature.

### 9.8 Legal-specific enrichment after ranking

The retriever can follow a narrow set of citations or implementation bridges to
fetch the exact governing provision. This is deterministic: it fetches a real
provision already present in Qdrant; it does not ask the LLM to invent a link.

The ranker also prevents repealed material from silently outranking an available
current provision. Historical law is not simply deleted because it may govern
older conduct, but it is labelled and treated carefully.

### 9.9 Relevance gate and corpus-gap detection

Vector search always finds the nearest item—even when every item is unrelated.
Therefore "Qdrant returned something" does not mean the corpus can answer.

The project checks query-focus coverage and distinctive terms. If no passage
actually addresses the question, it abstains. This is essential for avoiding a
grounded but irrelevant answer.

---

## 10. Fast lane: evidence-first retrieval

Fast mode is designed for a focused lookup.

```text
question -> normalization -> hybrid retrieval -> citation following
-> relevance/diversity gate -> evidence brief
```

It returns the closest governed passages, their excerpts and structured
citations. It deliberately says that it is an evidence brief and **does not
synthesize a final legal opinion**.

Fast citations have `verification_status="unverified"` because the claim-level
Deep verifier has not run. This is accurate labeling rather than implying that
retrieval alone equals legal verification.

Use Fast mode for:

- locating an Act or section;
- finding the closest authority;
- inspecting sources quickly;
- a simple, self-contained question.

---

## 11. Deep lane: the agentic LangGraph workflow

The graph is bounded and explicit:

```text
role_context
     -> query_understanding
     -> retrieval
     -> reasoning
     -> verification
          | pass
          v
     response_generation
          ^
          | weak result and retry remains
        retry -> retrieval
```

Maximum corrective retries: **2**.

This is not a group of autonomous bots chatting without control. It is a state
machine. Each node receives typed shared state, produces defined outputs and has
known transitions.

### 11.1 Shared agent state

The graph state carries:

- original and normalized query;
- role and optional case ID;
- selected specialist profile;
- conversation history;
- retrieved chunks and retrieval signature;
- draft claims;
- verification results;
- final citations and confidence;
- retry count, trace and timings.

This makes the workflow observable and testable.

### 11.2 Role-context node

The node selects a role profile and a specialist based on the question.

#### Citizen

Goal: plain-language rights, procedure and practical next steps.

Specialists:

- Procedure Navigator;
- Rights Explainer;
- Authority Finder.

#### Police

Goal: lawful, evidence-led investigation and procedural compliance.

Specialists:

- FIR Review;
- Evidence Integrity;
- Procedure Compliance;
- Case Evidence Search.

#### Advocate

Goal: two-sided research, authority mapping, weaknesses and lawful strategy.

Specialists:

- Defence Strategy;
- Authority Mapper;
- Evidence Challenge;
- Precedent Comparator.

#### Admin

Goal: neutral corpus inspection. Administrative access does not permit unsupported
legal claims or disclosure of unrelated private case data.

The specialists are prompt and workflow profiles over the same controlled graph;
they are not twelve separately trained models.

### 11.3 Query-understanding node

It identifies:

- intent;
- legal entities;
- language;
- complexity;
- a standalone retrieval query.

Example conversation:

```text
Earlier: What are the general rules for arrest?
Current: What about for a woman?
```

Searching only "What about for a woman?" loses the subject. Deep query
understanding resolves the back-reference. A self-contained short query can skip
the LLM and use deterministic extraction to save time.

### 11.4 Retrieval node

The first pass normally retrieves up to 24 candidates per collection and returns
up to 8 evidence chunks. A retry broadens the search, increases the candidate
window and asks for authoritative governing provisions.

For authorized police or advocate matters, the node searches both:

- the global legal corpus;
- the role-specific private collection filtered to the exact `case_id`.

It records whether evidence addresses the actual question. A low topical anchor
can trigger a fallback search, but new evidence is merged without discarding the
original topical anchor.

### 11.5 Reasoning node

The LLM is not asked for an unrestricted essay. It must return structured claims
in five categories:

1. direct answer;
2. legal basis;
3. application;
4. next step;
5. limit.

Every proposed claim must name one or more evidence labels corresponding to
retrieved chunk IDs. Unknown labels are discarded before verification.

Internal example:

```text
[LEGAL_BASIS] Police may arrest without warrant only under the stated
statutory conditions. [SRC:gold-chunk-abc123]
```

The prompt explicitly forbids inventing a section, case, fact, remedy, deadline
or citation. User-uploaded documents are treated as untrusted factual context,
not as legal authority or instructions.

### 11.6 Verification node

The verifier receives each claim with only the premise it cites and judges:

- `yes`: the passage directly supports the material claim;
- `partial`: support is incomplete;
- `no`: the passage does not support it.

It also rejects citation markers whose chunk ID was not in the retrieved set.
Only `yes` claims can reach the final answer. A partial compound claim is not
published because the program cannot know which words are safe.

This is **claim-level grounding**. It is stronger than attaching several sources
to the end of a paragraph and hoping they support everything.

### 11.7 Corrective retry

If no useful claims survive, the graph can broaden the query and retrieve again.
The loop is capped at two retries to prevent uncontrolled cost or infinite loops.

A retrieval signature records the evidence set. If a retry returns the same
evidence, reasoning and verification are skipped because repeating deterministic
generation cannot create new support.

### 11.8 Publication decision

Publication requires:

- at least one directly verified claim;
- more than caveats alone;
- a minimum claim-level support floor that rejects broadly fabricated drafts;
- evidence that addresses the user's question.

If these conditions fail, the result is an **abstention**: insufficient evidence
in the corpus. Abstention is a feature, not a system crash.

### 11.9 Response-generation node

The final response is rebuilt from the verified claim objects; it does not simply
reuse the original draft. This is crucial because the draft may contain rejected
claims.

Headings vary by role. For example:

| Category | Citizen | Police | Advocate |
|---|---|---|---|
| Legal basis | Why this is the legal position | Governing provision and legal basis | Authority and legal basis |
| Next step | What you can do now | Required procedural steps | Steps available |
| Limit | Important limits | Safeguards, limits and uncertainties | Contrary considerations, limits and gaps |

Currency checks then prevent known superseded material from grounding a live
claim and add notices for repealed or renumbered provisions.

---

## 12. How citations are created end to end

### 12.1 At ingestion time

Each chunk receives:

- stable chunk ID;
- title;
- Act/court;
- section/subsection;
- page start and end;
- verbatim text;
- source URL where available;
- currency and replacement information.

### 12.2 At reasoning time

The LLM may refer only to evidence labels mapped to the retrieved chunk IDs. An
invented label cannot resolve to a valid source and is dropped.

### 12.3 At verification time

Every claim-source pair is checked for entailment. Missing or fabricated source
IDs are penalized.

### 12.4 At response time

Only sources attached to surviving `yes` claims become `AgentCitation` objects.
The object includes:

- display number;
- `chunk_id`;
- title and source type;
- page range;
- Act, section or court;
- excerpt;
- retrieval score;
- verification status;
- current/repealed status;
- replacement and section-mapping details.

### 12.5 In the interface and database

The API returns answer text plus structured citation objects. PostgreSQL stores
the assistant message and citation JSON. The frontend can therefore show an
inspectable source card rather than relying on a fragile text-only footnote.

The trust chain is:

```text
Answer sentence
  -> verified claim
    -> retrieved chunk_id
      -> Qdrant payload
        -> canonical document + pages
          -> reviewed source PDF + provenance
```

---

## 13. Current-law handling

Legal truth is time-dependent. IPC, CrPC and the Indian Evidence Act were
replaced from 1 July 2024, but the older law may still govern earlier conduct.
Deleting all old law would also be wrong.

The system therefore distinguishes:

- current authority;
- repealed authority that may apply historically;
- still-operative material that cites a renumbered old provision;
- a provision not carried forward;
- status not yet verified.

Known superseded sources cannot silently ground a present-law claim. The user is
shown replacement dates and mappings where available. When metadata cannot prove
currency, the response carries a verification warning.

This is one reason legal RAG needs domain-specific metadata; generic semantic
similarity alone cannot determine which law is in force.

---

## 14. Security and privacy boundaries

The critical rule is that a private case collection is never searched without
the authorized role and exact case scope.

Threats addressed include:

- one user's case evidence leaking to another case;
- an admin role being treated as permission to read every private matter;
- a user-uploaded document injecting instructions into the LLM;
- private evidence being mistaken for public legal authority.

Controls include authentication, permission checks, Qdrant `case_id` filters,
separate collections, untrusted-document prompt boundaries, audit logs and tests
that mutate or remove tenant filters to confirm failures are detected.

---

## 15. Evaluation: how we know it works

### 15.1 Golden set

A **golden set** is a reviewed set of representative questions with expected
evidence or behavior. It is used to compare retrieval configurations such as:

- dense only;
- sparse only;
- hybrid RRF;
- hybrid plus reranking.

Important retrieval metrics include:

- **Recall@k**: did a relevant passage appear in the first `k` results?
- **MRR (Mean Reciprocal Rank)**: how early did the first relevant result appear?
- **Precision@k**: what fraction of the first `k` results were relevant?
- **nDCG**: did the system place highly relevant results above weaker ones?

### 15.2 Answer-level evaluation

Retrieval success does not guarantee answer success. The full pipeline also
measures or tests:

- citation validity;
- claim support;
- abstention on known corpus gaps;
- legal currency labels;
- private-case isolation;
- role-specific response structure;
- latency and resource use.

### 15.3 Why staging collections matter

A larger corpus is not automatically better. New documents can create duplicate
results, outdated conflicts or ranking noise. The correct lifecycle is:

```text
promote reviewed batch -> build versioned staging index -> validate
-> run regression/golden tests -> compare -> activate only if acceptable
```

The currently configured application collection and an in-progress rebuilt
collection can therefore differ. Never claim a downloaded or even built corpus
is live until configuration and quality gates confirm the cutover.

---

## 16. What makes the project technically strong

1. It separates candidate acquisition from trusted ingestion.
2. It preserves provenance, checksums and canonical identity.
3. It chunks along legal structure instead of arbitrary document boundaries.
4. It separates retrieval text from verbatim citation text.
5. It combines semantic and lexical retrieval with server-side RRF.
6. It uses metadata filters for jurisdiction, authority, currency and privacy.
7. It treats old law as time-sensitive rather than simply deleting it.
8. It checks whether evidence addresses the question, not merely whether search returned results.
9. It requires claim-to-chunk links before verification.
10. It reconstructs the answer only from directly verified claims.
11. It bounds retry and skips repeated work when evidence is unchanged.
12. It keeps Fast evidence lookup distinct from Deep verified synthesis.
13. It runs local models so legal text and questions need not leave the machine.
14. It exposes traces, timings and structured citations for auditability.

---

## 17. Honest limitations to present

A strong presentation states limitations clearly.

- Corpus coverage is incomplete and uneven across legal domains and jurisdictions.
- Source currency metadata still requires continued review.
- OCR can damage names, section numbers and punctuation.
- Retrieval may find the right topic but the wrong sub-issue.
- Claim verification is model-assisted, not a substitute for expert legal review.
- The local 14B model and Deep verification workflow can have high latency.
- Cross-encoder reranking is disabled by default because its cost has not been
  justified by measured gains on the current deployment.
- Downloaded candidates are not part of live answers until promotion, ingestion,
  validation and collection activation are complete.
- A role-specific response is not equivalent to personalized professional advice.

These limitations explain why the project uses abstention, source inspection,
confidence labels and professional-disclaimer boundaries.

---

## 18. End-to-end example you can explain on stage

Question:

> Can police arrest a person without a warrant?

### Offline work already completed

1. An official Act PDF was collected.
2. Its provenance, checksum, type, jurisdiction and status were recorded.
3. Text was extracted page by page; scanned pages used OCR.
4. The Act was parsed into sections.
5. The relevant section became one or more structure-bounded chunks.
6. Each chunk retained the Act name, section and page range.
7. `embed_text` added the Act and heading context.
8. BGE-M3 produced dense and sparse vectors.
9. Qdrant stored vectors, text and metadata.

### Online request

1. The API authenticates and safety-screens the request.
2. Auto routing sees a focused question and may choose Fast mode, unless the
   user requests Deep or additional complexity requires it.
3. Legal terms are normalized.
4. BGE-M3 embeds the question.
5. Qdrant searches dense and sparse indexes.
6. RRF fuses the result ranks.
7. Filters and legal enrichment favor eligible, current governing material.
8. A relevance gate checks that the passages truly concern arrest without warrant.

### If Deep Review is used

9. The citizen role selects a procedure/rights-oriented profile.
10. The reasoning node proposes a direct answer, legal basis, next steps and limits,
    each linked to retrieved chunk IDs.
11. The verification node checks each claim against its own passage.
12. Unsupported and partial claims are removed.
13. If nothing useful survives, retrieval may retry with a broader authoritative query.
14. The response is rebuilt from verified claims only.
15. Citation objects expose the Act, section, pages, excerpt and currency status.
16. If the corpus cannot support the answer, the system abstains.

---

## 19. Suggested R&D presentation structure

### Slide 1 — Title

**Corpusil: Verified Multi-Role Legal RAG for Indian Law**

Say: “Our objective is not merely to generate legal-looking text. It is to locate
inspectable authority, verify each claim and refuse unsupported answers.”

### Slide 2 — Problem

- legal information is large, scattered and time-sensitive;
- general LLMs can hallucinate;
- ordinary search does not synthesize or verify;
- private matter data needs strict isolation.

### Slide 3 — RAG from first principles

Explain corpus, chunk, embedding, vector search, retrieval and generation.

### Slide 4 — Why basic RAG is insufficient

Show failures: lexical mismatch, exact section terms, repealed law, irrelevant
nearest neighbor, unsupported LLM claim and private-data leakage.

### Slide 5 — Our type of RAG

Say the full label: domain-specific, multi-role, agentic hybrid RAG with
claim-level verification, corrective retry and abstention.

### Slide 6 — Full architecture

Show offline ingestion and online question-answering as two separate flows.

### Slide 7 — Data collection and governance

Explain official sources, candidate area, promotion, manifest, SHA-256,
de-duplication, language and currency review.

### Slide 8 — PDF to legal chunks

Show extraction, OCR, structural parsing, 700-token/80-overlap chunking and noise
rejection.

### Slide 9 — `text` versus `embed_text`

Use the Article 14 example. This is easy for the panel to understand and shows
a concrete engineering improvement.

### Slide 10 — Vectorization and Qdrant

Explain BGE-M3, 1,024-d dense vectors, sparse weights, payload metadata and the
separation between Qdrant, PostgreSQL and object storage.

### Slide 11 — Hybrid retrieval and RRF

Use one paraphrase example and one exact section-number example. Explain that
RRF combines ranks rather than incomparable scores.

### Slide 12 — Fast and Deep lanes

- Fast: source inspection and evidence brief;
- Deep: synthesis, claim verification and citations;
- low-confidence Fast results can escalate to Deep.

### Slide 13 — Role-based agents

Explain citizen, police, advocate and admin objectives and specialist profiles.
Clarify that these are controlled profiles in one graph, not uncontrolled bots.

### Slide 14 — Deep LangGraph

Show the nodes and bounded retry loop.

### Slide 15 — Claim-level verification

Show a proposed claim, `[SRC:chunk_id]`, verifier verdict and removal of a failed
claim. This is the core trust slide.

### Slide 16 — Citation chain and legal currency

Show answer -> claim -> chunk -> page -> PDF, plus handling of repealed and
renumbered law.

### Slide 17 — Security

Explain separate case collections, role + case filters, untrusted uploads and
auditing.

### Slide 18 — Evaluation

Discuss golden questions, retrieval metrics, citation checks, abstention tests,
privacy mutation tests and latency.

### Slide 19 — Limitations and current work

Be honest about coverage, metadata review, OCR and Deep latency. Explain that
corpus expansion uses staged promotion and versioned index validation.

### Slide 20 — Conclusion

Say: “The contribution is the evidence lifecycle: governed source acquisition,
legal-aware indexing, hybrid retrieval, role-aware reasoning, claim verification
and traceable citation.”

---

## 20. A five-minute explanation to memorize

> Corpusil is a local legal decision-support platform built around retrieval-
> augmented generation. A normal LLM generates from learned memory and can
> hallucinate, so our system first retrieves evidence from a controlled Indian-law
> corpus.
>
> The offline pipeline begins with official-source collection. Downloads remain
> candidates until their identity, provenance, checksum, language, duplication,
> document type and legal status are reviewed. Promoted PDFs are recorded in a
> canonical manifest. During ingestion, we verify the checksum, extract page text,
> use OCR for scanned pages, parse legal structure and create chunks within sections
> or other natural legal units. Each chunk keeps Act, section, court, pages, source
> and currency metadata. We embed a context-enriched form using BGE-M3 while
> preserving verbatim text for quotation.
>
> BGE-M3 produces both a 1,024-dimensional dense vector for semantic similarity and
> a sparse vector for exact legal terminology. Qdrant stores both vectors with the
> passage metadata. At query time, the question is normalized and embedded, dense
> and sparse searches run in Qdrant, and Reciprocal Rank Fusion combines their
> rankings. Metadata filters enforce jurisdiction, source, date, corpus tier and
> private case scope. A relevance gate allows abstention when the nearest passages
> do not actually answer the question.
>
> The system has Fast and Deep lanes. Fast returns an evidence brief and structured
> citations without claiming that it performed full verification. Deep uses a
> bounded LangGraph workflow: role context, query understanding, retrieval,
> reasoning, verification, optional corrective retry and response generation.
> Citizen, police, advocate and admin roles share the graph but receive different
> objectives, safety limits and output structure.
>
> During reasoning, the model must produce self-contained claims linked to retrieved
> chunk IDs. A verifier checks each claim only against its cited passage and labels
> it yes, partial or no. Only yes claims from eligible current sources are rebuilt
> into the final answer. Citations trace every surviving claim back to an Act or
> judgment, section, page range and excerpt. If the corpus lacks adequate evidence,
> the system abstains. Therefore the core contribution is not just generation; it
> is governed evidence collection, hybrid retrieval, claim-level verification and
> traceable publication.

---

## 21. Viva questions with clean answers

### Why use RAG instead of only an LLM?

Because an LLM is not an authoritative or current legal database. RAG provides
controlled, inspectable sources at answer time and enables citations and updates
without retraining the generator.

### Why not fine-tune the LLM with all PDFs?

Fine-tuning is useful for behavior and style, but it does not provide reliable
source tracing, easy deletion/update or guaranteed factual recall. RAG keeps
knowledge external, updateable and inspectable. Fine-tuning and RAG can coexist,
but they solve different problems.

### Why Qdrant?

It supports named dense and sparse vectors, metadata payload indexes, server-side
hybrid fusion, filters and asynchronous access. These match the project's need for
semantic search, exact legal terms and strict case/metadata constraints.

### Why hybrid retrieval?

Dense vectors capture meaning and paraphrases; sparse vectors protect exact legal
terms, sections and names. Legal questions need both.

### What is RRF?

Reciprocal Rank Fusion combines several ranked lists using the position of each
document. It avoids directly mixing dense and sparse raw scores, whose scales are
not comparable.

### What is the difference between retrieval and reranking?

Retrieval efficiently finds a candidate set from the whole corpus. Reranking uses
a more expensive model to reorder only those candidates. This project supports a
cross-encoder reranker, but it is off by default.

### What is agentic about the system?

LangGraph coordinates specialized nodes with shared state and conditional routing:
role selection, query understanding, retrieval, reasoning, verification, retry and
response generation. It is agentic but bounded and auditable.

### Are there twelve separate LLMs?

No. Specialist agents are role/task prompt profiles using the same underlying
workflow and local generation service. The distinction is their objective, safety
boundary and output contract.

### How do you prevent hallucinated citations?

The reasoning model can use only labels mapped to retrieved chunk IDs. Unknown IDs
are dropped. Verification checks every claim-source pair. The final response is
rebuilt only from directly verified claims, and citation metadata comes from the
retrieved payload rather than model memory.

### What if retrieval returns irrelevant material?

The relevance gate checks topical coverage and distinctive terms. The system can
retry with a broader query or abstain. Returning nearest neighbors alone is not
treated as sufficient evidence.

### What if a law is repealed?

The source remains available for historical questions, but currency metadata,
replacement mappings and publication rules stop it from silently grounding a
current-law claim.

### How is private case data protected?

It is held in separate role-specific collections and retrieved only for an allowed
role with an exact case-ID filter. Public law and private facts remain differently
classified, and uploads are treated as untrusted context rather than authority.

### Why have Fast and Deep modes?

Not every lookup needs slow multi-stage generation. Fast mode provides quick source
inspection; Deep mode pays extra latency for synthesis and claim verification.

### Why allow abstention?

A legal system should not convert a corpus gap into a confident answer. Abstention
is the correct outcome when evidence does not support a useful response.

### How do you update the knowledge base?

Review and promote a batch, ingest it into a versioned staging collection, validate
the index, run golden-set and domain regressions, compare it with the active index,
then switch configuration only after quality gates pass.

### What is the biggest current limitation?

Coverage and legal-currency verification remain continuous work. Deep verification
also has substantial local-model latency. These are handled through staged corpus
growth, explicit status labels, evaluation and separate Fast/Deep lanes.

---

## 22. Keywords to revise

### Foundation

AI, machine learning, LLM, token, context window, corpus, knowledge base, prompt,
hallucination, provenance.

### Data pipeline

candidate source, promotion, canonical manifest, SHA-256, de-duplication, PDF
extraction, OCR, structural parsing, chunk, overlap, enrichment, metadata,
checkpoint, cache, staging collection.

### Retrieval

embedding, vector, dense retrieval, sparse retrieval, semantic similarity, lexical
match, cosine similarity, IDF, hybrid search, RRF, metadata filter, candidate set,
reranker, cross-encoder, near-duplicate removal, relevance gate, small-to-big
retrieval, citation following.

### Agent pipeline

LangGraph, state machine, node, conditional edge, role profile, specialist agent,
query understanding, grounded reasoning, entailment, claim-level verification,
corrective retry, retrieval signature, publication gate, abstention.

### Evaluation and safety

golden set, Recall@k, Precision@k, MRR, nDCG, regression test, citation validity,
corpus-gap test, tenant isolation, prompt injection, audit log, latency, confidence,
legal currency, supersession.

---

## 23. Code map for technical questions

| Topic | Main implementation |
|---|---|
| Canonical document metadata | `backend/app/ingestion/metadata.py` |
| PDF extraction and OCR decision | `backend/app/ingestion/extract.py` |
| Legal structure parsing | `backend/app/ingestion/structure.py` |
| Chunk contract | `backend/app/ingestion/chunker.py` |
| BGE-M3 and embedding cache | `backend/app/ingestion/embedder.py` |
| Qdrant collection schema | `backend/app/ingestion/init_qdrant.py` |
| Qdrant payload/upsert | `backend/app/ingestion/qdrant_writer.py` |
| End-to-end ingestion | `backend/app/ingestion/pipeline.py` |
| Hybrid retrieval/RRF/reranking | `backend/app/services/retrieval.py` |
| Fast evidence lane | `backend/app/services/fast_research.py` |
| Fast/Deep automatic routing | `backend/app/services/adaptive_routing.py` |
| Role and specialist profiles | `backend/app/agents/role_profiles.py` |
| Deep graph | `backend/app/agents/orchestrator.py` |
| Query understanding | `backend/app/agents/query_understanding.py` |
| Agent retrieval | `backend/app/agents/retrieval_agent.py` |
| Structured grounded claims | `backend/app/agents/reasoning_agent.py` |
| Claim verification | `backend/app/agents/verification_agent.py` |
| Publication rule | `backend/app/agents/publication.py` |
| Final answer and citations | `backend/app/agents/response_generation.py` |
| Retrieval evaluation | `scripts/evaluate_retrieval.py` |

---

## 24. Final takeaway

Do not describe the project merely as “an AI chatbot for law.” That hides the
engineering contribution.

Describe it as an evidence system:

```text
governed sources
 -> reproducible ingestion
 -> legally structured chunks
 -> dense+sparse hybrid retrieval
 -> role-aware bounded reasoning
 -> claim-level source verification
 -> current-law-aware citations
 -> answer or honest abstention
```

That is the complete story from raw PDF to defensible output.
