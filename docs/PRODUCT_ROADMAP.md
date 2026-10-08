# Evidence-First Legal Intelligence Roadmap

This roadmap turns the current legal RAG platform into a fast, source-grounded legal intelligence product for citizens, police, and advocates. Work proceeds by quality gates: a milestone is complete only when its measurements pass, not when its code merely exists.

## Product promise

The system must:

1. Return the strongest available answer quickly.
2. Support each material factual and legal claim with an authoritative source.
3. Prefer current, jurisdictionally applicable law.
4. Remove unsupported claims or abstain when evidence is insufficient.
5. Keep every user's case material private.
6. Draft professional documents without inventing facts.
7. Support bail analysis and legal debate as evidence-constrained workflows.

Absolute zero hallucination cannot be guaranteed by an LLM. The enforceable product target is **zero unsupported published claims in the evaluated set**, backed by automatic abstention and visible uncertainty outside it.

## North-star measurements

These metrics are release gates, not dashboard decoration.

| Area | Measurement | Initial release target |
|---|---|---:|
| Retrieval | Governing-source Recall@20 | ≥ 95% |
| Retrieval | Supporting-passage Recall@20 | ≥ 95% |
| Citations | Citation precision | ≥ 98% |
| Answers | Material claims with entailing evidence | 100% |
| Currency | Repealed/superseded law presented as current | 0 critical errors |
| Safety | Cross-user or cross-case evidence leakage | 0 |
| Abstention | Unanswerable questions correctly refused | ≥ 95% |
| Drafting | Invented material facts | 0 |
| UX | Successful queries requiring technical configuration | 0 |
| Reliability | Restore test for accounts and case files | Pass |

Targets may be tightened after the baseline is measured. They must not be weakened merely to obtain a release.

## Current foundation

Already available:

- Hybrid dense and sparse retrieval with reciprocal-rank fusion
- Cross-encoder reranking
- Query understanding and guarded query expansion
- Citation following and supersession handling
- Claim verification, retry, confidence, and abstention paths
- Global, police, and advocate vector collections
- Case ownership and role isolation
- PostgreSQL, Qdrant, MinIO, Ollama, web, and Tauri architecture
- Canonical corpus inventory and acquisition evidence
- Correctness, frontend, security, and retrieval-oriented CI gates

This is the backbone. GraphRAG or another retriever must prove an improvement against it before becoming part of the production query path.

## Technology adoption rule

The roadmap is deliberately technology-agnostic. GraphRAG is optional, and no current component is protected from replacement. A technique is adopted when it produces a reproducible improvement on the blind legal evaluation while preserving source traceability, privacy, reliability, and the agreed latency budget.

Maintain a production baseline and one or more isolated challenger indexes. Test candidates in the following areas:

| Layer | Candidates worth evaluating | Required proof |
|---|---|---|
| OCR and parsing | Layout-aware OCR, table extraction, multilingual parsing | Better passage recovery and fewer corrupted provisions |
| Chunking | Section-aware, parent-child, semantic, contextual chunks | Higher governing-source and supporting-passage recall |
| Sparse retrieval | BM25 tuning, learned sparse retrieval such as SPLADE | Better exact provision, citation, name, and phrase matching |
| Dense retrieval | BGE-M3 challengers and legal-domain embeddings | Better semantic recall on Indian-law blind questions |
| Late interaction | ColBERT-style multi-vector retrieval | Better fine-grained legal matching at acceptable index and query cost |
| Fusion | Weighted RRF, query-dependent fusion, calibrated score fusion | Better combined ranking without hiding a weak retrieval lane |
| Reranking | Stronger cross-encoders, domain-tuned rerankers, listwise reranking | Higher top-result relevance and governing-source rank |
| Query transformation | Multi-query, decomposition, citation expansion, cautious HyDE | Better recall without topic drift or fabricated legal framing |
| Knowledge structure | Deterministic legal graph, GraphRAG, DRIFT-style search | Better relationship and corpus-wide answers with source-span evidence |
| Context construction | Diversity selection, parent expansion, evidence compression | More complete evidence with less distracting context |
| Reasoning | Structured claim plans, tool-routed workflows, model ensembles | Higher correctness without unsupported claims |
| Verification | Independent entailment, quotation, citation, and currency checks | Fewer unsupported or stale-law claims |
| Generation | Local and hosted model challengers where privacy policy permits | Better grounded drafting and reasoning at acceptable cost and latency |

Promotion procedure:

1. Register the hypothesis and the exact metric expected to improve.
2. Build the candidate behind a feature flag or separate index version.
3. Tune only on development and validation sets.
4. Run the untouched blind set and adversarial/privacy suites.
5. Measure accuracy, citations, abstention, latency, memory, storage, and operating cost.
6. Inspect regressions by user role, jurisdiction, document type, and question class.
7. Promote only when the gain is meaningful and no critical safety gate regresses.
8. Keep rollback available and record the model, prompt, index, corpus, and configuration versions.

A candidate may also be routed only to the question classes where it wins. For example, a graph retriever can serve precedent-relationship questions while the existing hybrid retriever continues to serve exact statutory questions.

## Execution order

### Milestone 1 — freeze the evaluation contract

**Purpose:** establish a trustworthy baseline before changing retrieval.

Deliverables:

- Create a versioned Indian-law evaluation set covering citizens, police, advocates, drafting, bail, conflicting authorities, current-law questions, and unanswerable questions.
- Record expected governing sources, supporting passages, jurisdiction, date, and required abstentions.
- Separate development, validation, and blind test sets.
- Measure retrieval, citation, answer, latency, and privacy metrics for the current system.
- Save every evaluation configuration, model version, corpus revision, and random seed.

Exit gate:

- Repeated runs produce a comparable baseline report.
- No retrieval or model change can merge without an A/B report against that baseline.

### Milestone 2 — corpus trust and legal currency

**Purpose:** make the knowledge base reliable before optimizing search.

Deliverables:

- Complete missing parent Acts and priority official sources.
- Validate provenance, file hashes, OCR quality, language, jurisdiction, authority, publication date, and current status.
- Link Act → chapter → section → proviso → schedule.
- Link old provisions to replacements and amendments with effective dates.
- Deduplicate official copies while preserving source provenance.
- Quarantine unreadable, unofficial, incomplete, or legally uncertain documents.
- Show corpus version and last-updated date in the product.

Exit gate:

- Every indexed document has required provenance and currency metadata.
- No quarantined file is reachable through production retrieval.
- Priority governing-law gaps have an owner and acquisition status.

### Milestone 3 — retrieval excellence

**Purpose:** maximize the probability that the correct law reaches the reasoning stage.

Deliverables:

- Replace flat chunks with section-aware, paragraph-aware, and parent-child chunks.
- Add compact contextual headers containing Act, section, jurisdiction, authority, date, document status, and parent heading.
- Preserve exact page and paragraph anchors through ingestion.
- Tune dense/sparse candidate sizes, RRF, deduplication, diversity, and reranking using the blind evaluation set.
- Evaluate legal-domain embeddings and ColBERT late interaction as offline challengers.
- Add retrieval explanations for operators: query variants, filters, scores, and rejected candidates.

Exit gate:

- Governing-source and supporting-passage Recall@20 meet their targets.
- The challenger improves accuracy without unacceptable latency or resource cost.
- Every returned chunk can open the original source at the supporting location.

### Milestone 4 — evidence-locked answer engine

**Purpose:** prevent fluent text from outrunning the evidence.

Deliverables:

- Generate a structured claim ledger before rendering prose.
- Require source IDs for every material legal and factual claim.
- Run entailment verification claim by claim.
- Delete unsupported claims; qualify partial support; abstain when the remaining evidence cannot answer.
- Distinguish binding law, persuasive authority, official guidance, user facts, allegations, and model analysis.
- Detect citation mismatch, quotation mismatch, authority conflict, and stale-law risk.
- Display source excerpts, page/paragraph anchors, authority, date, and current-status warnings.

Exit gate:

- Evaluated answers contain zero unsupported published material claims.
- Citation precision meets target.
- All deliberately unanswerable test questions abstain or request the missing information.

### Milestone 5 — fast, hassle-free product experience

**Purpose:** hide retrieval complexity without hiding evidentiary limits.

Deliverables:

- One primary input with automatic role, task, jurisdiction, and depth routing.
- Automatic Quick and Deep modes; technical settings stay out of the normal user journey.
- Stream status progressively: understanding, researching, verifying, drafting.
- Cache embeddings, stable retrieval results, corpus metadata, and repeated public-law queries safely.
- Run independent retrieval work concurrently.
- Provide source preview, copy citation, save to case, continue research, and export actions beside the answer.
- Make failure states actionable: missing facts, unavailable source, conflicting authority, or insufficient evidence.

Exit gate:

- Users can complete core flows without configuring models, collections, or servers.
- Latency percentiles are recorded separately for Quick and Deep workflows.
- Cancellation, retry, refresh, and partial-service failure paths work without losing user data.

### Milestone 6 — evidence-safe document drafting

**Purpose:** create professional legal documents without invented facts or fake authorities.

Deliverables:

- Build structured templates for the first approved document types.
- Use guided fact intake with required, optional, disputed, and unknown fields.
- Maintain a fact/source matrix linking each pleaded fact to user input or case evidence.
- Maintain a proposition/authority matrix linking legal submissions to verified sources.
- Insert visible placeholders for missing facts instead of completing them speculatively.
- Support redlining, version history, clause-level regeneration, DOCX, and PDF export.
- Run a final consistency check across names, dates, amounts, sections, prayers, annexures, and citations.

Exit gate:

- Golden drafting cases contain no invented material facts or unverifiable citations.
- A professional reviewer can trace every material fact and proposition to its source.
- Exported documents pass visual and structural verification.

### Milestone 7 — bail analysis workspace

**Purpose:** provide a structured, balanced bail analysis—not an unjustified outcome prediction.

Deliverables:

- Intake offences, custody dates, filing status, antecedents, co-accused parity, medical facts, investigation status, and risk allegations.
- Calculate relevant statutory/default-bail dates from confirmed inputs.
- Retrieve jurisdiction-specific binding and persuasive authorities.
- Produce favourable factors, adverse factors, prosecution position, defence position, missing evidence, possible conditions, and draftable grounds.
- Treat outcome likelihood as qualified analysis, never as fact or guarantee.

Exit gate:

- Date calculations pass boundary tests.
- Every legal factor and precedent is cited.
- Missing decisive facts cause a request for information or qualified output, not invention.

### Milestone 8 — controlled virtual legal debate

**Purpose:** stress-test a case while keeping advocacy separate from evidence.

Deliverables:

- Defence and opposing-side agents receive the same locked factual record and source set.
- Each argument identifies its facts, assumptions, authority, and requested inference.
- A rebuttal stage challenges applicability, jurisdiction, currency, and evidentiary support.
- A neutral evaluator produces an issue matrix, strongest points, weaknesses, unresolved disputes, and evidence still required.
- A final verifier removes unsupported propositions from every side.

Exit gate:

- No agent introduces an unlabelled fact outside the locked record.
- Every legal proposition is traceable to a verified authority.
- The evaluator does not present a simulated result as a real judicial prediction.

### Milestone 9 — legal graph and selective GraphRAG

**Purpose:** improve relationship-heavy and corpus-wide research without weakening exact-source retrieval.

Deliverables:

- Build a source-grounded graph for statutes, provisions, amendments, judgments, citations, followed/distinguished/overruled treatment, parties, courts, and dates.
- Retain source span and confidence for every edge.
- Route relationship questions to graph retrieval and broad thematic questions to GraphRAG/DRIFT-style analysis.
- Always return to original passages for final evidence.
- Keep exact statutory and pinpoint-citation questions on the proven hybrid retrieval path.

Exit gate:

- Graph retrieval wins on a dedicated relationship-query test set.
- Unsupported graph edges cannot become answer evidence.
- Added indexing and query cost stays inside the measured product budget.

### Milestone 10 — private pilot and production launch

**Purpose:** validate the system with real workflows before public exposure.

Deliverables:

- Run a private pilot with a small, approved group of citizens, police users, and advocates using non-sensitive or properly authorized matters.
- Collect structured feedback and failure reports, not only satisfaction scores.
- Test encrypted backups, restores, retention, deletion, incident response, and audit review.
- Harden HTTPS ingress, cookies, CSRF, upload scanning, rate limits, secret management, monitoring, and alerting.
- Complete privacy, licensing, professional-use, and jurisdictional legal review.
- Publish signed Tauri clients and the website only after release gates pass.

Exit gate:

- No unresolved critical accuracy, privacy, authorization, backup, or source-provenance defect.
- The release candidate passes the blind evaluation and restore drill.
- Operations has rollback, incident, and corpus-update procedures.

## Workstreams that continue through every milestone

- Corpus acquisition and provenance review
- Red-team testing for leakage, prompt injection, citation fabrication, and unsafe files
- Accessibility and plain-language explanations
- Performance profiling and cost measurement
- User feedback triage
- Documentation and operator runbooks
- Model, prompt, corpus, and index versioning

## What not to do

- Do not replace the current retriever because a newer RAG architecture is fashionable.
- Do not let an LLM-generated graph become legal authority.
- Do not optimize answer fluency before governing-source recall.
- Do not publish a draft with invented placeholders silently filled.
- Do not mix user allegations with verified facts.
- Do not expose PostgreSQL, Qdrant, MinIO, Ollama, or private case files directly to clients.
- Do not claim zero hallucination without an evaluated definition and abstention policy.

## Immediate next sprint

Execute these tasks before adding another major user-facing feature:

1. Freeze the first version of the evaluation schema and scoring rules.
2. Author the first 100 expert-reviewed questions, including at least 20 unanswerable/adversarial cases.
3. Run the current system and publish the baseline retrieval, citation, answer, latency, and abstention report.
4. Identify the top ten retrieval failure patterns.
5. Implement contextual hierarchical chunks behind an index version flag.
6. Re-index into a challenger collection without replacing production.
7. A/B the challenger against the baseline.
8. Promote it only if the quality gates improve and privacy remains intact.

Only after this sprint should the team choose between further retrieval tuning, ColBERT, or the first legal-graph prototype.
