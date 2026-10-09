# Coverage-driven corpus and answer-quality plan

Date: 2026-10-08  
Owners: Codex (coverage, acquisition, evidence) and Claude (measured query-path optimisation)

## Decision

The project no longer treats **2,500 PDFs** as a success target. Document count
is inventory information only. Collection stops and starts according to
workflow failures: a new source is acquired when a supported citizen, police,
or advocate task lacks authoritative evidence, not because the repository has
not reached an arbitrary volume.

The product contract is:

> Answer supported legal workflows from current, authoritative evidence with
> claim-level citations. If that evidence is absent, conflicting, stale, or
> jurisdiction-dependent, state the limitation instead of inventing an answer.

This means the objective is not literally zero abstentions. It is zero
**avoidable** abstentions and zero measured unsupported legal claims.

## Baseline we can defend

The metadata-only workflow audit is reproducible with:

```bash
python3 scripts/coverage_gap_audit.py
```

Current metadata result across 22 defined workflows after the 530-document
promotion:

| State | Workflows |
|---|---:|
| Canonical manifest complete | 22 |
| All sources acquired but awaiting review/promotion | 0 |
| Partially covered | 0 |
| Completely uncovered | 0 |

All 10 P0 workflows and all 12 P1/P2 workflows have their minimum sources in
the canonical manifest. This does not yet mean the live runtime is ready: the
new `global_legal_corpus_v5` index is still building, while users remain on
`v4`. The promoted sources become runtime-ready only after the complete-index,
payload, retrieval, answer, citation, currency, and latency gates pass.

The remaining source-quality work is narrow:

1. OCR and validate the 101 unique canonical documents flagged
   `ocr_required`, prioritising the current tax material and the largest
   high-value instruments. This is a measured processing queue, not a request
   to collect 101 replacement PDFs.
2. Assemble later final amendments to the official Central Motor Vehicles
   Rules historical consolidation before calling it current.
3. Attach authoritative commencement/rules evidence for the Andhra Pradesh
   tenancy Act before treating its provisions as operative.
4. Reclassify the 453 unique canonical documents that currently sit in the broad
   `primary_law/other_relevant_laws` bucket where narrower routing is justified.
5. Expand the scenario bank and let measured failures—not PDF count—drive the
   next acquisition batch.

The existing golden set contains 61 questions: 29 citizen, 25 police, and only
7 advocate questions. That is enough for regression detection, not enough to
prove broad legal readiness.

Latest stored measurements relevant to quality:

| Measure | Stored result | Interpretation |
|---|---:|---|
| Retrieval recall@5 | 92.7% | Strong, but misses are still too frequent for high-stakes use |
| Retrieval recall@20 | 96.4% | Candidate generation still has gaps |
| Retrieval MRR | 0.745 | Relevant authority often appears early |
| Answer/abstention correctness | 88.5% | Below release quality |
| Unsupported claims | 0 | Preserve this gate |
| Authored ground coverage | 47.7% over only 8 graded items | Ground annotations are too sparse and coverage is too low |
| Currency correctness | 65% over 20 graded items | The largest measured legal-quality risk |
| Answer-quality p50 | 53 s | Too slow for ordinary use; Claude is measuring Fast and Deep separately |

Sources: `docs/evidence/retrieval-eval-v3-current.json` and
`docs/evidence/answers-after-gate-fix.json`.

## A workflow is ready only when every gate passes

### 1. Authority and coverage gate

- Every minimum source is official and canonical.
- Jurisdiction and legal status are explicit.
- Parent Act, implementing rules, commencement, and material amendments are
  connected when the workflow needs them.
- Legacy or repealed law is labelled and cannot silently outrank current law.

### 2. Retrieval gate

- P0 workflow recall@5: at least 95%.
- P0 workflow recall@20: at least 99%.
- No current-law query ranks a repealed or merely proposed instrument above
  the governing source.
- Section-number and natural-language paraphrases both retrieve the authority.

### 3. Answer and citation gate

- At least 97% correct answer-versus-abstain decisions on supported scenarios.
- Zero unsupported legal claims in the release evaluation set.
- Every material legal proposition has a citation to the supporting passage.
- At least 90% coverage of authored expected grounds.
- A citation verifier must reject answers where the cited passage does not
  entail the claim.

### 4. Currency gate

- At least 95% currency correctness across a meaningfully graded set.
- Current, amended, repealed, transitional, and not-yet-commenced instruments
  are distinguishable.
- Time-sensitive sources have a review date and refresh owner.

### 5. Persona and usability gate

- Citizen answers explain the next safe action in plain language.
- Police answers separate legal power, preconditions, procedure, safeguards,
  documentation, and supervisory escalation.
- Advocate answers expose competing authority, procedural posture, limitation,
  jurisdiction, and adverse precedent instead of flattening the issue.
- Fast mode remains concise; Deep mode adds genuine analysis rather than
  merely producing more words.

### 6. Drafting and debate gate

- Drafts use only supplied facts and verified legal propositions.
- Missing facts remain marked fields; the model never invents names, dates,
  allegations, annexures, sections, or precedents.
- Bail and virtual-debate modes produce arguments for both sides, identify the
  burden and disputed facts, and cite every legal proposition.
- Every generated draft includes a verification checklist before export.

## Execution loop

### Loop A — Establish the supported surface

Maintain `data/source_materials/coverage_requirements_v1.json`. The generated
audit distinguishes canonical, staged, downloaded candidate, manifest-only,
and missing sources. A candidate never counts as runtime-ready.

### Loop B — Expand the evaluation bank

For every P0 workflow, author at least:

- 6 ordinary answerable scenarios;
- 2 ambiguous or missing-fact scenarios;
- 2 wrong-jurisdiction, stale-law, or adversarial scenarios;
- coverage across the personas who use that workflow.

For P1 and P2, begin with six scenarios per workflow and expand wherever
failures cluster. Every scenario records expected governing sources, expected
provisions or propositions, currency requirements, and whether abstention is
correct.

### Loop C — Classify every failure

| Failure class | Owner and action |
|---|---|
| Governing source absent | Codex acquires the official source |
| Source downloaded but not safe/current | Claude reviews; Codex supplies provenance evidence |
| Source canonical but not retrieved | Claude adjusts retrieval, metadata filters, chunking, or reranking |
| Correct evidence retrieved but answer wrong | Claude adjusts reasoning, prompts, or verification |
| Citation does not support claim | Block publication and repair citation verification |
| Jurisdiction/facts genuinely insufficient | Preserve a precise abstention and request the missing fact |

### Loop D — Re-measure before expanding

After each domain-sized change:

1. Run retrieval evaluation.
2. Run answer/citation/currency evaluation.
3. Compare Fast and Deep latency on the same query set.
4. Publish the evidence report.
5. Collect more material only for remaining source-gap failures.

## Retrieval architecture direction

Keep the current hybrid dense+sparse retrieval and improve the quality gates
around it. Use metadata filtering, section-aware parent/child retrieval,
reranking, query decomposition, current-law resolution, contradiction checks,
and claim-level citation verification.

Graph retrieval is selective, not compulsory. Add a legal relationship graph
where it materially helps multi-hop tasks:

- Act → section → rule → notification;
- instrument → amendment → commencement → repeal/savings;
- judgment → proposition → followed/distinguished/overruled treatment;
- offence → ingredients → exception → punishment → procedure;
- remedy → forum → jurisdiction → limitation → appeal.

Do not graph every paragraph or delay high-value coverage work for a wholesale
GraphRAG migration. It earns its place only when the evaluation set shows a
measurable improvement over hybrid retrieval.

## Current owner split

| Lane | Codex | Claude |
|---|---|---|
| Coverage | Requirements, gap audit, official-source acquisition | Acceptance and runtime-readiness review |
| Corpus mutation | None | Promotion and ingestion after benchmark windows |
| Retrieval | Failure evidence and expected sources | Retrieval/chunking/reranking fixes |
| Quality | Scenario specification and source-ground expectations | Answer, citation, currency, and abstention measurement |
| Performance | Stay out of Ollama/BGE/Qdrant during measurement | Fast/Deep profiling and measured optimisation |

The demonstrated source gaps are now acquired as review candidates, not as a
bulk PDF target. The five pending workflows move through review first. The
motor-vehicle base text is explicitly historical, and the Andhra Pradesh
tenancy Act remains commencement-sensitive; neither warning may be removed
without authoritative currency evidence.
