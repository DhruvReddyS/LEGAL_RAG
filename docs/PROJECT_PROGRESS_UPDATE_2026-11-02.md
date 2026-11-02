# Corpusil — full project progress update

**Status date:** 2 November 2026 (Asia/Kolkata)

**Repository:** `DhruvReddyS/LEGAL_RAG`

**Branch reviewed:** `main` at `42c9aeb`, plus the working-tree evidence listed below
**Release position:** the product workflows are implemented, but v5 is **not approved for cutover** because the complete release gate suite has not passed.

This update separates implemented code, measured evidence, incomplete work, and blocked verification. A feature being present in code is not treated as release-ready unless its applicable gates have passed.

## 1. Executive status

| Area | Current status |
|---|---|
| Application | Citizen, police, advocate, and admin workspaces are implemented |
| Web/desktop delivery | Next.js web UI and Tauri desktop shell are implemented; no public marketing/compliance website yet |
| Backend | FastAPI application with role-based access, retrieval, case workflows, durable Deep jobs, audit/security controls, and ingestion operations |
| Serving corpus | `global_legal_corpus_v4`, 49,684 points (last recorded serving state) |
| v5 candidate | Built successfully: 1,563/1,563 canonical documents, 133,857 points, green collection, zero ingestion failures |
| v5 cutover | **Not complete**; v4 remains live |
| v5 gates | Payload/currency passed; retrieval quality failed; answer run stopped at 8/61; four later gates not run |
| Frontend verification on 2 Nov | **44/44 tests passed**; production build, lint, and TypeScript checks passed |
| Backend verification on 2 Nov | **Infrastructure-blocked before test bodies**; PostgreSQL role missing and Docker daemon stopped |
| Latency evidence | Fast p50 0.09 s / p95 0.18 s; Deep p50 64.95 s / p95 142.47 s on v4 benchmark environment |
| Main performance improvement | Deep first useful, source-backed output reduced from 64.66 s to 0.57 s p50; final answer time is unchanged |

## 2. What is built

### 2.1 Shared platform and trust layer

- Accounts, roles, JWT sessions, rate limiting, and audit logging.
- Tenant/case isolation controls and structural ownership checks on case routes.
- Fast retrieval lane and Deep LangGraph lane with adaptive routing.
- Durable Deep-review jobs, event delivery, cancellation, and persisted results.
- Hybrid BGE-M3 dense/sparse retrieval, reciprocal-rank fusion, statutory concordance, citation following, and coverage-based abstention.
- Claim verification, claim-level citations, official-source links, currency/repeal labelling, and unsupported-claim blocking.
- Document upload and analysis, source inspection, answer history, and follow-up routing.
- Corpus acquisition, validation, deduplication, OCR routing, chunking, embedding, ingestion monitoring, and release-gate tooling.
- Next.js static-export UI and Tauri desktop packaging/updater scaffolding.

### 2.2 Citizen workflow

- Plain-language and voice question intake.
- Source-backed legal answers with openable citations.
- Immediate-danger/refusal screening and abstention when the corpus lacks support.
- Per-section grounding, document upload/analysis, session history, and follow-up questions.

### 2.3 Police workflow

- Isolated case register and evidence uploads.
- FIR fact extraction and drafting.
- Nine persisted BNSS investigation deadlines.
- BNSS compliance record covering 24 general and four conditional requirements.

### 2.4 Advocate workflow

- Private case corpus.
- Defence strategy with adverse arguments.
- Authority mapping and four specialist personas.

### 2.5 Admin and operations

- User management, corpus intake, statistics, and audit-log interfaces.
- Lightweight ingestion-status API and frontend status page.
- Rebuild progress reporting and recovery/keeper scripts.
- Seven-part corpus release gate runner plus volume-versus-ranking analysis.

### 2.6 Corpus v5 work completed

- All 1,563 canonical documents were ingested with zero failed documents.
- Candidate collection reached 133,857 points and reported green.
- Doubled-text chunks were reduced from 61 to zero.
- 353 citation-furniture chunks were reviewed and pruned, leaving zero detected.
- Five doubled/unsearchable source documents were routed through OCR and re-ingested.
- Payload/currency validation passed: all 1,563 expected canonical documents indexed, all recorded URLs present, no missing currency-note keys.

## 3. What is not built or not finished

### 3.1 Release-critical work

1. Finish the v5 gate suite and preserve every result.
2. Resolve the retrieval citation-accuracy regression before cutover.
3. Complete the 61-item answer evaluation; the recorded attempt stopped at item 8.
4. Run provision reach, retrieval health, latency, and provision-drift checks on v5.
5. Decide whether the retrieval baseline should move from v3 to v5, with a documented reason; it must not be re-recorded only to turn a failed gate green.
6. Approve or reject v5 promotion. Until then, v4 remains the serving collection.
7. Create golden set v4 using document identities instead of phrase-only predicates.
8. Profile the unexplained ingestion memory pressure that forced most of the 43-hour v5 build onto CPU.
9. Repair the keeper process guard whose broad `pgrep` match can mistake monitoring commands for a worker.

### 3.2 Shared platform gaps

- Email verification, password reset, professional MFA, and device management.
- DPDP consent, data-principal requests, retention/erasure, and grievance handling.
- Answer export/print with citations intact.
- Searchable/pinnable/organised history.
- Deep progress over SSE instead of polling.
- Human legal-aid/advocate fallback after abstention.
- Complete offline corpus pack, accessibility, low-bandwidth mode, and formal information-not-advice framing.

### 3.3 Website gaps

- Public landing page, install/download page, privacy notice, terms, help pages, and route split between the public site and authenticated app.

### 3.4 Citizen gaps

- Upload redaction, notice/summons explainer, printable rights guide, safe forum/limitation router, additional drafting formats, multilingual support, guided journeys, legal-aid routing, and matter deadlines/reminders.

### 3.5 Police gaps

- Cross-case deadline register, evidence-backed compliance records, broader drafting set, offence-ingredient checklist, search/seizure legality check, chain of custody and witness tracking, supervisory dashboard, and court-ready export.

### 3.6 Advocate gaps and data blockers

- Bail workflows, drafting library, matter calendar, briefs, and synopsis generation.
- Precedent research, citator, opponent-authority checking, and factual case comparison are blocked by corpus breadth/history data.
- The current recorded corpus has only 93 judgments (79 Supreme Court and 14 Andhra Pradesh High Court); it is not sufficient for reliable nationwide precedent features.

### 3.7 Admin gaps

- Release console, corpus coverage/currency/OCR work queues, quality and latency dashboard, feedback/incident triage, full account controls, end-to-end retention/deletion, and model/prompt A/B configuration.

### 3.8 Corpus/data gaps

- Judgments at useful Supreme Court and High Court volume.
- State-law coverage beyond the currently claimed scope.
- Overruling and subsequent-history data.
- Incremental add/replace/retire ingestion, amendment watch, change notifications, and proactive expert review.

## 4. Test and build report — 2 November 2026

### 4.1 Frontend

Commands run from `frontend/`:

```text
npm test
npm run build
```

| Check | Result |
|---|---|
| Node test runner | **PASS — 44/44 tests, 0 failures** |
| Next.js production compilation | **PASS** |
| ESLint/build lint phase | **PASS** |
| TypeScript validity check | **PASS** |
| Static page generation | **PASS — 7/7 pages** |

Generated routes included `/`, `/design-system`, and `/ingestion` (plus the framework not-found route). The build used Next.js 14.2.35.

### 4.2 Backend

Attempted command:

```text
.venv-ingest/bin/python -m pytest backend/tests -q
```

Result: **not a valid test run**. The suite-wide setup fixture tried to connect to PostgreSQL at `localhost:5432` and failed with:

```text
asyncpg.exceptions.InvalidAuthorizationSpecificationError:
role "legal_rag" does not exist
```

The Docker daemon was also unavailable, so the repository's PostgreSQL/Qdrant/MinIO stack could not be started. The run was stopped after 64.73 seconds and 358 setup errors; these are repeated infrastructure setup errors, not 358 independent application test failures. No backend pass count is claimed for this update.

Documentation currently contains two stale historical totals—902 tests in `01-PRODUCT.md` and 956 in `03-EVIDENCE.md`. The next successful clean backend run should become the single authoritative count and both documents should be reconciled.

### 4.3 v5 release gates already recorded

| # | Gate | Result |
|---|---|---|
| 1 | Payload/currency | **PASS** |
| 2 | Retrieval quality | **FAIL** |
| 3 | Answer quality | **INCOMPLETE** — stopped at 8/61, all eight recorded `unsup 0` |
| 4 | Provision reach | **NOT RUN** |
| 5 | Retrieval health | **NOT RUN** |
| 6 | Latency | **NOT RUN on v5** |
| 7 | Provision drift | **NOT RUN** |

Retrieval gate detail:

| Metric | Baseline | v5 result | Decision |
|---|---:|---:|---|
| Recall@5 | 0.927 | 0.909 | within configured tolerance |
| Citation accuracy@5 | 0.638 | 0.602 | **regression; gate failed** |
| Advocate recall@5 | 0.714 | 0.714 | unchanged |
| Citizen recall@5 | 0.957 | 0.957 | unchanged |
| Police recall@5 | 0.960 | 0.920 | watch/regression |

The current baseline is v3 from 6 September 2026. Separate analysis says v5 beats v4 on all retrieval metrics except recall@20, but that comparison does not override the configured release gate.

## 5. Latency report

### 5.1 Measurement context

The latest complete, auditable latency benchmark was recorded on 8 October 2026 against `global_legal_corpus_v4` (49,684 points), not v5. Environment: Apple M5 Pro with 24 GB unified memory; BGE-M3 on MPS; Qdrant 1.18.2; local `qwen3-14b-16k` at temperature 0; seven frozen queries, three repeats each, after one discarded warm-up per mode.

### 5.2 End-to-end results

| Metric | Fast | Deep |
|---|---:|---:|
| p50 | **0.09 s** | **64.95 s** |
| p95 | **0.18 s** | **142.47 s** |
| Minimum / maximum | 0.03 / 0.21 s | 30.5 / 150.5 s |
| Time to first useful output, p50 before change | 0.09 s | 64.66 s |
| Time to first useful output, p50 after change | unchanged | **0.57 s** |
| Configured budget | 5 s | 300 s |
| Measured runs | 21 | 21 |

Fast is comfortably inside its budget. Deep's final answer latency remains high, but it now exposes located, explicitly unverified authorities as soon as retrieval finishes, reducing the wait for useful source-backed information from about a minute to about half a second at p50.

### 5.3 Where Deep time goes

| Stage | p50 | Share |
|---|---:|---:|
| Reasoning LLM | 52.40 s | 80.7% |
| Verification LLM | 10.10 s | 15.6% |
| Retrieval | 0.086 s | 0.1% |
| Retrieval enrichment | 0.016 s | approximately 0% |
| Response assembly | 0.002 s | approximately 0% |

Approximately 97% of Deep latency is local model work. Recorded model throughput was 14.4 output tokens/second, with a median 675 output tokens, 7,965 prompt tokens, and 2.86 model calls per query. The 142-second p95 is driven by a useful verification/reasoning retry on the broad Article 14 question, not by queueing or retrieval.

### 5.4 Performance changes retained

- Publish located authorities immediately after retrieval: first useful Deep output p50 **64.66 s → 0.57 s**; final answer time unchanged.
- Overlap term-frequency lookup with search: about 0.016 s p50 and 0.044 s p95 saved.
- Warm the query embedder until timings flatten, avoiding first-request kernel/allocation cost.
- Reverted a verifier verdict-count prompt change after measurement showed fewer citations and more insufficient answers, even though it reduced retries. Quality was prioritised over a misleading speed gain.

### 5.5 Latency limitations and next measurement

- These numbers are v4 evidence and must not be presented as v5 performance.
- The laptop thermally throttles; recorded decode rate changed by 58% between runs, so Deep comparisons require throughput beside elapsed time.
- A new v5 latency result is required after the other gates and on an idle, cool, mains-powered host with no queued jobs or corpus process.

## 6. Current risks and decisions

| Risk/decision | Why it matters | Owner/action |
|---|---|---|
| v5 retrieval gate failed | Citation accuracy declined against the configured baseline | Diagnose or explicitly approve a justified baseline change; do not auto-promote |
| Golden set uses phrase predicates | A quoted provision can look like the governing authority was found | Build CORP-07 / golden set v4 with document identities |
| Backend suite not rerun cleanly | Current code-level regression status is unknown | Start the correct test services/role and run the full suite |
| Deep final latency | p50 about 65 s; p95 about 142 s | Keep early-source streaming; compare faster models only with quality gates |
| Judgment/history coverage | Blocks reliable precedent and citator features | Product owner decides licensing/acquisition scope |
| State-law scope | Product claims must match acquired law | Product owner names supported states |
| Limitation guidance | A wrong deadline can cause loss of rights | Decide required conservatism before building C-05 |
| DPDP/public pages absent | No place yet for required notice and grievance information | Build WEB-01 to WEB-05 with PLAT-05 |

## 7. Recommended next sequence

1. Restore a valid local test stack and run the complete backend suite; reconcile the documented test count.
2. Resume the v5 gate suite from answer quality, then run provision reach, retrieval health, latency, and provision drift.
3. Investigate the retrieval citation-accuracy and police recall regressions item by item against v4 and the configured v3 baseline.
4. Decide and document whether to fix ranking or deliberately re-record the baseline.
5. Promote v5 only after all required gates pass and the cutover decision is recorded; otherwise keep v4 serving.
6. After release stabilization, implement the public/compliance website and DPDP/account-recovery work before expanding feature breadth.
7. Acquire judgment, subsequent-history, and state-law data only after licensing and product-scope decisions.

## 8. Evidence used for this update

- `docs/01-PRODUCT.md`
- `docs/03-EVIDENCE.md`
- `docs/06-PLAN.md`
- `docs/evidence/gates/v5-cutover/HANDOFF.md`
- `docs/evidence/gates/v5-cutover/RETRIEVAL_GATE_ANALYSIS.md`
- `docs/evidence/gates/v5-cutover/payload.txt`
- `docs/evidence/gates/v5-cutover/retrieval-gate.txt`
- `docs/evidence/latency/LATENCY_EVIDENCE_REPORT.md`
- Frontend test/build output captured on 2 November 2026
- Backend test attempt and local service diagnostics captured on 2 November 2026

