# Citizen Global Legal Corpus RAG — Technical Report and Viva Guide

**Report date:** 31 August 2026  
**Project:** Multi-Agent Legal RAG Decision Support Platform  
**Audience:** project guide, evaluator, developer and demo operator  
**Status:** the ingestion, retrieval, citation and guarded-answer pipeline is working; a claim of 100% legal accuracy is **not** yet justified because the hand-graded Phase 2 accuracy evaluation and complete current-law validation are still pending.

## 1. The project in one simple sentence

The Citizen system searches a locally stored collection of Indian legal material, selects the most relevant passages, asks a local Ollama model to explain only those passages, verifies every proposed claim against its cited passage, and then shows a structured answer with inspectable sources.

It is not a normal chatbot that answers only from model memory. The legal documents remain the evidence base.

## 2. What is proven working today

| Area | Observed result | Meaning |
|---|---:|---|
| Physical source records | 419 | PDFs and their source metadata were inventoried. |
| Canonical documents | 381 | 38 exact duplicate copies were removed from the compute path. |
| Canonical pages | 17,426 | Pages represented after deduplication. |
| Native text pages | 13,448 | Text was read directly from the PDF. |
| OCR-selected pages | 3,978 | Tesseract text was used when it improved weak native extraction. |
| Documents using OCR | 100 / 381 | At least one page needed OCR in these documents. |
| Legal chunks | 25,517 | Searchable, page-linked units. |
| Dense embeddings | 25,517 | One 1,024-dimensional BGE-M3 dense vector per chunk. |
| Sparse embeddings | 25,517 | One BGE-M3 learned lexical vector per chunk. |
| Qdrant Gold points | 25,517 | Every accepted chunk is represented in the live vector collection. |
| Strict ingestion issues | 0 | The accepted ingestion validation found no payload/vector integrity issue. |
| Retrieval smoke suite | 12 / 12 passed | The original Gold hybrid-retrieval acceptance suite passed. |
| Current backend suite | 129 / 129 passed | Observed on 31 August 2026; one Passlib deprecation warning remains. |

The live `global_legal_corpus` collection reported `green` status with 25,517 points on 31 August 2026.

## 3. Honest limits: why “100% correct” is not claimed

The software now prevents many common RAG failures, but legal correctness has more than one layer:

1. **Retrieval correctness:** did the search locate the right passage?
2. **Entailment correctness:** does the passage actually support the generated claim?
3. **Citation correctness:** does the displayed source point to that passage?
4. **Currency correctness:** is the provision or judgment still current and applicable?
5. **Fact/application correctness:** were the user's facts understood without adding assumptions?

The system verifies layers 2 and 3 in the Deep workflow and warns when layer 4 is unverified. Phase 2 must measure all layers against a manually prepared legal answer key. Until that evaluation exists, the accurate statement is:

> “The Citizen RAG pipeline is operational, source-grounded and guarded, but its legal accuracy percentage has not yet been measured.”

Known corpus qualifications:

- the manifest contains 26 of 27 mandatory items; the standalone Advocates Act, 1961 PDF is the recorded gap;
- some Gold payloads do not yet have independently verified current-law status;
- an unverified-current source produces a visible **Source currency** warning;
- a source explicitly marked superseded is not allowed to publish a user-facing claim;
- the missing-pet Fast test now abstains because the corpus does not contain sufficiently local pet-specific support; it no longer substitutes missing-child passages.

## 4. End-to-end architecture

```text
Official / curated legal PDFs
        |
        v
Manifest + SHA-256 deduplication
        |
        v
PyMuPDF text extraction ---- weak page ----> Tesseract OCR
        |                                      |
        +---------------- cleaned page text ---+
                           |
                           v
Legal structure parser: headings / sections / pages
                           |
                           v
700-word-unit chunks, 80-unit overlap, stable chunk IDs
                           |
                           v
BAAI BGE-M3: dense 1,024-D vector + learned sparse vector
                           |
                           v
Qdrant global_legal_corpus + legal metadata + original text
                           |
          Citizen question + JWT role boundary
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
Fast evidence mode                    Deep Review job
Qdrant full-text lane                 LangGraph multi-stage workflow
No LLM claim generation               BGE hybrid retrieval + reranker
          |                                 |
          v                                 v
Cited evidence or abstention          Ollama reasoning -> verification
                                            |
                                            v
                                  Structured verified answer
                                  + citations + currency warning
```

## 5. Stage A — source collection and organisation

Each physical source has metadata such as title, source URL, authority, source type, checksum and whether it came from an official source. SHA-256 checksums identify byte-for-byte duplicate PDFs.

Measured corpus quantities:

| Quantity | Physical view | Canonical compute view |
|---|---:|---:|
| Documents | 419 | 381 |
| PDF bytes | 691,556,372 | 641,658,344 |
| Pages | 19,632 | 17,426 |
| Exact duplicate copies | 38 | excluded from repeated OCR and embedding |

“Canonical” means one accepted compute copy represents all identical physical copies. The mapping is retained, so deduplication saves work without losing provenance.

Major canonical categories include 82 Acts, 41 Rules, 110 government-guidance documents, 18 police manuals, 79 Supreme Court judgments, 14 High Court judgments, 24 Law Commission reports and the Constitution.

## 6. Stage B — PDF extraction and OCR

The extraction decision is page-specific:

1. PyMuPDF first attempts native text extraction.
2. If a page produces fewer than 40 useful characters, Tesseract OCR is attempted.
3. OCR is selected only when it improves the page text.
4. Page number and extraction provenance remain attached to the text.

Observed extraction results:

- 13,448 pages (77.17%) used native PDF text;
- 3,978 pages (22.83%) used selected Tesseract OCR output;
- 100 of 381 canonical documents needed OCR on at least one page;
- all 381 canonical documents completed;
- extracted JSON occupies 77,870,633 bytes.

The original artifact timestamps span 1 hour 9 minutes 17 seconds, but that window includes extraction, OCR, parsing and chunk writing. Separate exact OCR-only and chunking-only durations were not recorded, so they must not be presented as measured timings.

## 7. Stage C — legal-aware chunking

### Why chunk at all?

An entire 300-page Act or judgment is too large and too broad to search or send to an LLM. Chunking breaks it into smaller evidence units. A good chunk should contain enough local meaning while remaining specific enough to cite.

### How this chunker works

The parser first tries to preserve legal structure—headings, sections, subsections and page ranges. If one structural unit is too large, the fallback splits it into windows of at most 700 whitespace-delimited word units with an 80-unit overlap.

The overlap prevents an important sentence at a boundary from losing the context immediately before it. These counts are whitespace units, not BGE tokenizer tokens.

Every chunk carries:

- stable `chunk_id`;
- document and canonical-document IDs;
- title and source type;
- court, jurisdiction, Act and section when available;
- heading path;
- start and end page;
- current-status and official-source flags;
- the chunk text.

The stable ID is derived from canonical document identity, structural position, page range and text. This supports reproducible citations and safe replacement.

### Measured chunk statistics

| Metric | Observed value |
|---|---:|
| Chunks | 25,517 |
| Average chunks per canonical document | 66.97 |
| Total Unicode characters | 41,062,887 |
| Total whitespace words | 6,021,060 |
| Minimum words/chunk | 1 |
| Median words/chunk | 111 |
| Mean words/chunk | 235.96 |
| p75 | 411 |
| p90 / p95 / maximum | 700 / 700 / 700 |
| Chunk JSONL size | 67,865,517 bytes |

The estimated tokenizer-dependent corpus volume is 8.01–10.27 million tokens. This is explicitly an estimate, not a measured tokenizer count.

## 8. Stage D — BGE-M3 embeddings

### Simple explanation

An embedding converts text into numbers that represent meaning. Similar legal ideas should be closer in the vector space even when their wording is not identical.

BAAI `bge-m3` produces two representations for each chunk:

1. **Dense vector:** 1,024 floating-point values for semantic similarity.
2. **Learned sparse vector:** token IDs and weights for strong lexical/legal-term matching.

Using both is called hybrid retrieval. Dense search helps with paraphrases; sparse search helps with exact terms such as section numbers, Act names and legal phrases.

### Measured embedding inventory

- 25,517 dense embeddings;
- 25,517 sparse embeddings;
- 381/381 complete, valid per-document embedding caches;
- 194,659,528 bytes of compressed durable embedding cache;
- approximately 6.40 GiB unique local BGE model cache;
- zero invalid complete or partial caches in the accepted validation.

The original cumulative active embedding duration was not recorded. A measured stable Apple MPS window processed 505 chunks in 193.48 seconds, equal to 156.6 chunks/minute. At that measured rate, the full corpus represents approximately 2 hours 43 minutes of active optimized work. The broader first-to-last project window was 22 hours 50 minutes 26 seconds and included pauses, retries, experiments and idle time, so it is not GPU compute time.

## 9. Stage E — Qdrant storage

Qdrant stores one logical point per chunk in `global_legal_corpus`.

Each point contains:

- the 1,024-dimensional dense vector;
- the sparse vector with IDF modifier;
- the original chunk text;
- page and source metadata needed for citations;
- governance fields such as corpus tier, official verification and currency status.

The live collection uses cosine distance for dense similarity, HNSW indexing (`m=16`, `ef_construct=100`), on-disk payloads and one local shard/replica for this capstone deployment.

The other collections, `police_case_data` and `advocate_case_data`, are private case stores. A Citizen query is routed only to `global_legal_corpus`; it cannot add a private collection merely by placing a case ID in the prompt.

## 10. What happens when a Citizen asks a question

There are two deliberately different modes.

### 10.1 Fast evidence mode

Purpose: return inspectable evidence quickly without generating a legal conclusion.

Current flow:

1. remove generic question words and retain legal focus terms;
2. run bounded Qdrant full-text searches in parallel;
3. rank candidate passages by local 50-token-window coverage;
4. require distinctive concepts to co-occur—for example, `missing` with `dog/pet`, or `Article` with `14`;
5. return diverse source cards, or abstain;
6. do not call Ollama and do not generate new legal claims.

This split was introduced after a cold three-request BGE benchmark measured Fast p95 of 8,489.1959869 ms. On the final mixed run, the evidence-only lexical lane measured Fast p95 of 92.944966 ms. The missing-pet benchmark correctly returned zero citations because the candidates were not pet-specific enough.

Fast mode is therefore a rapid source-discovery tool, not a ChatGPT-style final answer.

### 10.2 Deep Review mode

Purpose: produce the professional, structured assistant answer.

Deep Review is submitted as a durable job. The HTTP request returns quickly, while the frontend follows saved Server-Sent Events for progress. The job survives page refreshes and can be cancelled.

The LangGraph workflow is:

1. **Role context:** applies the Citizen profile and safety boundary.
2. **Query understanding:** Ollama extracts intent, legal concepts and a retrieval query.
3. **Hybrid retrieval:** BGE-M3 creates dense and sparse query vectors; Qdrant performs dense, sparse and reciprocal-rank-fusion retrieval.
4. **Reranking:** `bge-reranker-v2-m3` reads the query/candidate pairs and reorders them; Deep normally keeps the best five chunks on the first pass.
5. **Reasoning:** Ollama receives the question plus retrieved evidence. It must return structured, self-contained claims, each linked to one to three exact retrieved chunk IDs.
6. **Verification:** a separate Ollama call checks each claim/chunk pair as `yes`, `partial` or `no`.
7. **Bounded retry:** if verification confidence is below 0.5, retrieval/reasoning may retry, with a maximum of two retries.
8. **Deterministic response generation:** only `yes` claims are published. Partial and unsupported claims are removed.

## 11. How the Ollama integration works

The backend connects to the Ollama HTTP API at `OLLAMA_BASE_URL`. In the current local setup, the backend container reaches the Mac-host Ollama service through `http://host.docker.internal:11434`.

Current model configuration:

- model: `qwen3-14b-16k:latest`;
- context window: 16,384 tokens;
- hidden thinking: disabled;
- temperature: 0.0 for repeatability;
- reasoning output ceiling: 1,800 tokens;
- generation concurrency: 1 so local model requests queue predictably;
- streaming HTTP internally, with time-to-first-response-token telemetry;
- output is not shown to the user until claims have passed verification.

Why use Ollama?

- model inference remains local;
- no per-request commercial API charge or remote token quota is required;
- the model can be replaced through configuration;
- network transmission of the legal prompt to a third-party LLM is avoided in the local deployment.

Ollama is the model server, not the legal database. Qdrant supplies the evidence; Ollama interprets and explains it under constraints.

## 12. How the final answer is made professional and safe

The model does not directly write unrestricted Markdown. It first returns a typed claim structure with these categories:

- direct answer;
- legal basis;
- application to the stated facts;
- next step;
- important limit.

Every claim must cite exact retrieved chunk IDs. Unknown IDs are discarded. The verifier then checks each claim against each source. A deterministic renderer builds the Citizen response:

- **Direct answer**
- **Why this is the legal position** (only when verified legal-basis claims exist)
- **How this applies to you**
- numbered **What you can do now**
- **Important limits**
- **Source currency** when current status is unverified

The final visible citations become `[Source 1]`, `[Source 2]`, and so on, with title, pages, excerpt, retrieval score, verification status and current-status metadata available to the UI.

The answer is designed to sound like an assistant, not like a debug report: it never mentions chunks, embeddings, retrieval or RAG to the Citizen.

## 13. Why the prompt alone is not the safety system

Prompt instructions help, but production safety also requires code-level enforcement:

| Risk | Code-level control |
|---|---|
| Invented citation ID | Only IDs present in retrieved hits are accepted. |
| Mixed supported/unsupported sentence | Claims are verified independently; `partial` is not published. |
| Superseded authority | Explicitly superseded sources cannot publish a claim. |
| Unverified legal currency | A visible source-currency warning is appended. |
| Weak evidence | The response becomes an explicit insufficient-evidence message. |
| Prompt requests private data | Citizen retrieval targets only the global collection. |
| Long request blocks browser | Deep work is a durable background job with SSE progress. |
| Too many local generations | Ollama concurrency is bounded and per-user rate limits apply. |

## 14. Real performance evidence

Final mixed one-Deep/three-Fast run (`phase1-mixed-load-run-09.json`):

| Metric | Observed value |
|---|---:|
| Deep enqueue HTTP | 16.737542 ms |
| First durable progress | 536.505708 ms |
| Fast p95 | 92.944966 ms |
| Deep end-to-end | 235,215.636292 ms |
| Deep workflow | 233,746.464148 ms |
| Deep citations | 2 |
| Ollama response token rates | 11.443645154694439, 9.60993120119558, 9.734470021989763 tokens/s |
| Ollama first-response-token times | 6,907.058545, 31,022.947055, 41,971.07727 ms |

Two queued Deep jobs (`phase1-queued-deep-run-01.json`):

| Position | Queue wait | Service | End-to-end | Citations |
|---:|---:|---:|---:|---:|
| 1 | 182.095 ms | 332,972.397 ms | 333,154.492 ms | 2 |
| 2 | 333,166.63 ms | 209,936.002 ms | 543,102.632 ms | 2 |

The second job obeyed the approved “queue wait + 300,000 ms” contract. However, the two-job service p95 is 326,820.57725 ms, above the 300,000 ms ceiling. Phase 1 therefore remains open. This is primarily a local 14B model throughput issue, not an HTTP/job durability failure.

## 15. Security and role boundary for Citizen RAG

1. Authentication uses JWT access/refresh credentials.
2. The backend obtains the trusted role from the authenticated user, not from arbitrary prompt text.
3. Citizen has no private case collection target.
4. Police and Advocate private retrieval requires the correct role and explicit case ownership/scope.
5. The global corpus is shared read-only evidence; each user's chat and private data remain separate.
6. Browser auth uses HttpOnly cookies; tokens are not written to `localStorage`.
7. This is decision-support information, not a substitute for a qualified professional reviewing the complete current law and facts.

## 16. How to run and verify it

From the repository root:

```bash
docker compose --env-file .env -f docker/docker-compose.yml up -d --build
docker compose --env-file .env -f docker/docker-compose.yml ps
curl --fail http://localhost:8000/health
curl --fail http://localhost:6333/collections/global_legal_corpus
```

Validate the stored corpus:

```bash
QDRANT_URL=http://localhost:6333 LEGAL_KB_ROOT="$PWD/data/legal_kb" \
  PYTHONPATH="$PWD/backend" .venv-ingest/bin/python \
  -m app.ingestion.validate --require-complete
```

Run retrieval smoke tests offline from the local model cache:

```bash
QDRANT_URL=http://localhost:6333 LEGAL_KB_ROOT="$PWD/data/legal_kb" \
  HF_HOME="$PWD/data/legal_kb/cache/models" HF_HUB_OFFLINE=1 \
  TRANSFORMERS_OFFLINE=1 PYTHONPATH="$PWD/backend" EMBEDDING_DEVICE=auto \
  .venv-ingest/bin/python -m app.ingestion.retrieval_smoke
```

Run the backend tests in the same container runtime used by the project:

```bash
docker compose --env-file .env -f docker/docker-compose.yml run --rm --no-deps \
  -e TRUSTED_HOSTS=test,localhost,127.0.0.1 \
  -e S3_PUBLIC_ENDPOINT_URL=http://minio:9000 \
  -v "$PWD/backend:/app" backend env -u COOKIE_SECURE python -m pytest -q
```

## 17. Recommended Citizen demo questions

Use Deep Review when you want a structured answer:

1. “Police declined to register information that I believe discloses a cognizable offence. What supported procedural options are available, what facts are still missing, and what are the limits of the retrieved authority?”
2. “Explain Article 14 in plain language. Separate the verified legal rule, how it may apply, and any important uncertainty. Cite every claim.”
3. “A person says their dog is missing. What can this corpus safely support about making a complaint or FIR, and where must the system abstain?”
4. “A complainant has only screenshots and forwarded messages. What can the retrieved law safely say about preserving and proving electronic evidence? Do not assume authenticity.”
5. “Someone asks about a section that does not exist. Do not guess; explain whether the corpus provides reliable support.”

For the missing-dog question, abstention or carefully limited general procedure is better than a confident but irrelevant answer.

## 18. Two-minute explanation for the project guide

> “We built a local Retrieval-Augmented Generation system for Indian legal decision support. We collected 419 source records and deduplicated them into 381 canonical documents. PyMuPDF extracted normal PDF text, while Tesseract was selected for 3,978 weak-text pages. A legal-aware parser preserved headings, sections and page ranges, then created 25,517 chunks with a maximum of 700 word units and an 80-unit overlap. BGE-M3 converted every chunk into a 1,024-dimensional semantic vector and a learned sparse lexical vector. Both vectors and the original citation metadata are stored in Qdrant.
>
> When a Citizen requests Deep Review, LangGraph first understands the query, retrieves with dense and sparse search, fuses the rankings, reranks candidates, and sends only the selected evidence to a local Qwen 14B model through Ollama. The model must produce typed claims tied to exact chunk IDs. A separate verification call checks every claim against its cited passage. Code then removes partial or unsupported claims and builds a structured answer with source cards and a current-law warning when needed. Citizen requests can access only the shared global corpus, not police or advocate private data. The pipeline and 129 backend tests pass, but we are not claiming 100% legal accuracy until the Phase 2 hand-graded evaluation and current-law validation are complete.”

## 19. Likely viva questions and short answers

### Why not give the whole PDF to the LLM?

It would exceed the context window, increase latency and mix unrelated provisions. Retrieval selects smaller page-cited evidence units.

### Why both dense and sparse vectors?

Dense vectors handle meaning and paraphrases. Sparse vectors preserve exact legal words, section numbers and names. Hybrid search is stronger than using only one.

### Why rerank after Qdrant retrieval?

Initial vector search is fast but approximate. The cross-encoder reads the query and candidate passage together and improves the final ordering for Deep Review.

### Why a separate verifier?

The reasoning model may overstate evidence. Verification turns every claim/source pair into an explicit decision, and code publishes only fully supported claims.

### Does the model know the law by itself?

The model has general pretrained knowledge, but the application instructs it to answer from retrieved evidence. The displayed legal claims must survive source verification.

### Is the system offline?

After the PDFs, BGE models, Ollama model and containers are installed, the application can run locally without a cloud LLM. Initial downloads and software installation require connectivity.

### Is it 100% accurate?

No accuracy percentage has been measured yet. The correct claim is that the pipeline is grounded and guarded. Phase 2 will measure citation precision/recall, hallucination and abstention correctness against a human answer key.

### Why is Deep mode slow?

It runs query understanding, neural retrieval/reranking, structured reasoning and separate verification on a local 14B model. Durable jobs make it usable, but one queued test exceeded the 300-second service ceiling; model/runtime optimization remains open.

## 20. What must happen next

In authoritative plan order:

1. close the remaining Phase 1 service-latency breach without weakening grounding;
2. build the 25–30 item hand-graded Phase 2 evaluation set;
3. have a law student, guide or advocate independently review 8–10 blinded outputs;
4. validate current-law metadata and add/update missing primary authorities, including the recorded standalone Advocates Act gap;
5. publish `ACCURACY_EVALUATION.md` with measured citation precision, citation recall, abstention correctness and hallucination rate.

## 21. Key implementation files

- Corpus assessment: `docs/INGESTION_ASSESSMENT.md`
- Ingestion pipeline: `backend/app/ingestion/pipeline.py`
- OCR/text extraction: `backend/app/ingestion/extract.py`
- Legal chunker: `backend/app/ingestion/chunker.py`
- BGE embedder: `backend/app/ingestion/embedder.py`
- Qdrant collection schema: `backend/app/ingestion/init_qdrant.py`
- Retrieval service: `backend/app/services/retrieval.py`
- Fast evidence mode: `backend/app/services/fast_research.py`
- LangGraph workflow: `backend/app/agents/orchestrator.py`
- Reasoning claim contract: `backend/app/agents/reasoning_agent.py`
- Verification: `backend/app/agents/verification_agent.py`
- Citizen response renderer: `backend/app/agents/response_generation.py`
- Ollama boundary: `backend/app/services/llm.py`
- Durable jobs and SSE: `backend/app/services/job_worker.py`, `backend/app/routers/jobs.py`
- Raw performance evidence: `docs/evidence/`

## 22. Final defensible conclusion

The Citizen global-corpus RAG is genuinely implemented: the corpus is extracted, OCR-assisted, structurally chunked, embedded, indexed, searchable, role-scoped, locally generated, claim-verified and citation-rendered. It has real validation and performance evidence.

The remaining work is not to “make RAG exist.” It is to prove legal accuracy on a hand-graded set, improve current-law governance, and bring worst-case local Deep service time under the approved ceiling. That distinction is important and academically defensible.
