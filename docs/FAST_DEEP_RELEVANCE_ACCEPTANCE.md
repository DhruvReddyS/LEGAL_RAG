# Fast/Deep Relevance Fix Acceptance

Status: **ACCEPTED for this scoped fix cycle**

This record closes only the POCSO/Fast-honesty/auto-escalation fix cycle. It does not change the separately recorded Phase 1 latency status.

## Implemented behavior

### Before

- Fast confidence was `min(0.78, 0.48 + 0.08 × unique_documents)`. Four distinct documents therefore produced `0.78` even when the documents were irrelevant to the question.
- Every Fast citation was assigned `verification_status="verified"`, although Fast never calls the claim/source verifier.
- Relevance anchors were topic-specific. A query containing an unrecognized distinctive legal term could fall through to a generic two-term match.
- A retry in Deep Review rebuilt its retrieval query from the original user text, which reintroduced a typo after query understanding had corrected it.

### Accepted implementation

- Fast confidence is now:

  `min(0.85, (0.7 × mean_local_coverage + 0.3 × focus_term_recall) × mandatory_term_match_rate)`

- Document count is recorded for audit/diversity but is not a confidence input.
- Query presentation words are removed before legal focus analysis.
- Qdrant document frequencies identify the distinctive legal focus term. A result must contain that term locally; zero-frequency terms cannot be bypassed by generic matches.
- Known Act acronyms are matched generically against either the acronym or the governed full Act-name expansion. The same mechanism covers POCSO, NDPS, IPC, CrPC, BNS, BNSS and BSA; there is no POCSO query special case.
- A named Act's primary legislation is prioritized over secondary references when its full title matches the requested acronym expansion.
- Fast citations are `unverified`, because Fast performs source discovery and relevance scoring, not claim verification.
- Fast scores below `0.6` publish no Fast result. The backend queues a durable Deep Review job against the same chat session and the UI displays `Searching more thoroughly…` with job progress.
- Fast scores from `0.6` to below `0.75` are `moderate`; scores at or above `0.75` are `strong`.
- Deep query understanding applies a unique one-edit/Damerau transposition correction against the known legal acronym vocabulary. Corrections are auditable in the agent trace and are preserved through every retrieval retry.
- Deep citation status now keeps the strongest claim verdict for a shared chunk (`yes > partial > no`) instead of allowing a later weaker verdict to overwrite an earlier verified claim.

## Required acceptance results

### A. Known strong Article match stays Fast — PASS

Query: `Article 14 equality`

- Delivery: `complete`
- Response mode: `fast`
- Confidence: `0.7666666666666666`
- Evidence strength: `strong`
- API total: `56.16 ms`
- Client elapsed: `67.237125 ms`
- Distinctive term: `equality`
- Mean local coverage: `0.6666666666666666`
- Focus-term recall: `1.0`
- Mandatory-term match rate: `1.0`
- Citation status: `unverified`, accurately reflecting retrieval-only Fast mode

Raw evidence: `docs/evidence/fast-deep-relevance-fix-strong-fast-rerun-raw.json`

### B. Correctly spelled POCSO query surfaces the primary Act first — PASS

Query: `how to file a pocso case`

- Delivery: `complete`
- Response mode: `fast`
- Confidence: `0.7071428571428571`
- API total: `49.71 ms`
- Client elapsed: `58.012084 ms`
- First authority: `The Protection of Children from Sexual Offences Act, 2012`
- Second authority: `Age of Consent Under The Protection of children From Sexual Offences Act,2012 17 th September 2023 Click Here`
- Both Fast citation statuses: `unverified`

Raw evidence: `docs/evidence/fast-deep-relevance-fix-acceptance-attempt-02.json`

### C. Misspelled POCOS query resolves to a cited explanation — PASS

Query: `how to file a pocos case?`

- Fast delivery: `searching_more_thoroughly`
- Fast client elapsed before job handoff: `130.893417 ms`
- Deep terminal status: `succeeded`
- Deep job elapsed: `262253.398917 ms`
- Normalization trace: `pocos` → `POCSO`
- Retrieval query 0: `how to file a POCSO case`
- Retrieval query 1: `how to file a POCSO case POCSO governing law authoritative provision`
- Published confidence: `0.8`
- Published evidence strength: `moderate`
- Final answer sections: Direct answer; legal position; application; practical next step; source-currency qualification
- Cited authority: `IN RE: RIGHT TO PRIVACY OF ADOLESCENTS vs SMW(C) No. 3/2023`, whose retrieved passage reproduces POCSO Act section 19 reporting duties
- Citation status: `verified`

The answer instructs the user to report the offence to the Special Juvenile Police Unit or local police, explains who may report, and describes the cited care/protection and reporting steps. It is not the abstention response.

Raw evidence: `docs/evidence/fast-deep-relevance-fix-typo-rerun-raw.json`

### D. Genuinely unsupported query still abstains — PASS

Query: `What licensing procedure applies to teleportation booths on Mars?`

- Fast confidence: `0.0`
- Fast citations published: `0`
- Fast delivery: `searching_more_thoroughly`
- Fast API total: `92.72 ms`
- Deep terminal status: `succeeded`
- Deep job elapsed: `288125.958042 ms`
- Deep confidence: `0.0`
- Deep citations: `0`
- Final answer: `I could not find enough reliable support in the indexed legal corpus for this answer.`

Raw evidence: `docs/evidence/fast-deep-relevance-fix-acceptance-attempt-02.json`

### E. Confidence and labels are tied to match quality — PASS

Before, the bad POCSO result received `0.78` from four unique documents and every citation was hardcoded `verified`.

After:

- Strong Article example: `0.7666666666666666`, computed from `0.6666666666666666` mean local coverage, `1.0` recall and `1.0` mandatory match; labelled `strong`; citations labelled `unverified`.
- Correct POCSO example: `0.7071428571428571`, with the distinctive legal entity satisfied and the primary POCSO Act ranked first; citations labelled `unverified`.
- Unsupported example: `0.0`, because mandatory `teleportation` had corpus frequency `0` and no result satisfied the gate; no citations were returned and Deep Review was triggered.

These examples demonstrate that neither confidence nor verification status depends on document diversity alone.

## Automated verification

- Full backend suite after the final code change: **142 passed**, **1 warning**, elapsed `18.83 s`.
- The warning is the existing Passlib/Python `crypt` deprecation warning; it is not a test failure.
- Production Next.js static build: **passed** after the auto-escalation UI changes.
- `git diff --check`: **passed**.

## Preserved failed evidence

- `docs/evidence/fast-deep-relevance-fix-acceptance-attempt-01.json` preserves the original normalized-query run that still reintroduced `pocos` on retry and abstained.
- `docs/evidence/fast-deep-relevance-fix-acceptance-attempt-02.json` preserves the later run in which the answer succeeded but exposed the shared-chunk citation-status aggregation bug. Its automated case-C flag remains false; it has not been rewritten.
- The final case-C pass is independently recorded in `docs/evidence/fast-deep-relevance-fix-typo-rerun-raw.json`.

## Qualification

Fast remains a source-discovery preview and deliberately does not call Ollama or claim verification. A Fast result can have strong relevance while its citations remain honestly `unverified`. Deep Review is the explanatory, generated and claim-verified path.
