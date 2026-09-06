# What to do next

*6 September 2026, evening. The v3 rebuild is complete and deployed; the
answer-quality re-measurement is running.*

## Where things stand

| | |
|---|---|
| Corpus | `global_legal_corpus_v3`, 24,810 points, deployed |
| Backend tests | 919 |
| Red-team | 36, re-run against v3 tonight, all pass |
| Frontend | 38 tests, one palette, both themes |
| Citizen | feature-complete |
| Police | investigation workflow complete |
| Advocate | complete except the parked debate room |

Baselines are recorded in `docs/evidence/`. Both CI gates are wired.

## 1. Ground coverage — 0.474, and the cause is now located

This is the next fix and it is well understood, so it should be quick.

Answers that publish name **under half** the statutory grounds. On
`arrest-current-law` the answer gives six of the ten grounds in BNSS s.35(1)
and misses *proclaimed offender* and *stolen property* — **both of which were
retrieved**.

Three things were ruled out and one found, by reading the code rather than
guessing:

- **Not the evidence window.** `reasoning_node` receives every retrieved hit,
  not a top-5 slice. All eight passages reach the model.
- **Not truncation.** Each passage carries 1,800 characters, and the missing
  grounds sit inside that.
- **Not retrieval.** Both grounds were in the retrieved set.
- **It is `MAX_CLAIMS = 10`.** Ten claims spread across five categories is
  roughly two per category. BNSS s.35(1) enumerates ten grounds. The answer
  cannot list ten grounds in two claims, so the cap is a hard ceiling on
  coverage for any enumerative question — which is most statutory questions.

### Why raising it is safe now and was not this morning

The cap was coupled to the abstention gate. Verification counts one
**claim-marker pair** per citation, not per claim, so a well-sourced claim
citing three passages produced three pairs. More claims and better sourcing
both pushed the denominator up, the ratio down, and the answer into
"insufficient evidence". Raising `MAX_CLAIMS` would have increased the
abstention rate.

That coupling is gone: publication now depends on absolute sufficiency, not on
the ratio. So the cap can be raised on its own merits.

**Suggested next step:** raise `MAX_CLAIMS` to 16–20, measure ground coverage
and latency together, and watch the verification stage — it is the cost that
scales, one LLM call per batch of pairs.

Note in passing: `VerificationResult.total_claims` holds the pair count, not
the claim count. It feeds a published metric under a misleading name.

## 2. Latency — 102.6 s p50 against a 90 s target

The publication fix should reduce this on its own: a broad question no longer
retries twice before being discarded, and `child-needing-care` spent 332
seconds doing exactly that. That is a prediction, and the re-measurement will
settle it. Do not tune latency until it lands — raising `MAX_CLAIMS` will push
in the other direction, and the two must be read together.

## 3. The currency questions still retrieve nothing

`theft-current-law` and `evidence-current-law` return no BNS or BSA passage in
the top 20. The metadata is correct — 370 BNS and 180 BSA chunks carry the
right act name — so this is retrieval matching **topic** where the question is
about **currency**. 164 years of commentary discusses IPC theft; the BNS
provision appears in one document. A rank penalty of 3 does not close that gap.

Worth trying, in order of how little they distort other queries:

1. Detect the currency question deterministically ("which law now governs",
   "is X still in force") and filter to in-force sources for those queries only.
2. Route them through the section mapper instead of retrieval: the concordance
   already knows IPC s.378 → BNS s.303, and the answer is a mapping, not a
   passage.

The second is more honest — the question *is* a concordance lookup — and it
reuses work that already exists.

## 4. Reading grade 14.4 on a citizen surface

Undergraduate level for an audience that includes people with no legal
training. Statutory prose is polysyllabic by nature so the figure runs high for
any correct answer, but this is not where a citizen surface should sit. Note
that a previous attempt to improve answers by prompt change took ground
coverage from 0.67 to 0.50, so change one thing and measure it.

## Waiting on you

1. **The five corpus gaps** — [CORPUS_GAPS.md](CORPUS_GAPS.md). Three of the
   four hosts carrying those Acts are unreachable from this machine, so this
   needs either a network path or the PDFs dropped into
   `data/legal_kb/raw/primary_law/civil_gaps/`. For tenancy it also needs a
   State; Andhra Pradesh is the corpus's existing lean.
2. **The debate room**, parked. §15 of the PRD has the cost.

## Not worth doing yet

Adding features. Every module has working features and a measured quality
problem; another surface makes the second harder to see.
