# Retrieval gate: why it failed, and what the failure means

*10 October 2026, `global_legal_corpus_v5`, 133,857 points.*

## The failure as reported

```
citation_accuracy_at_5: 0.638 -> 0.602 (-0.036)   REGRESSION
recall_at_5:            0.927 -> 0.909 (-0.018)   ok
```

## The baseline is two corpus generations old

`docs/evidence/quality-baseline.json` was recorded on **6 September against
`global_legal_corpus_v3`** — 25,323 points. v4 was evaluated on 2 October and
the baseline was never re-recorded, so the gate has been comparing every
subsequent corpus against v3.

Measured against the v4 evaluation that does exist
(`docs/evidence/retrieval-eval-v4.json`):

| metric | v3 baseline | v4 | **v5** | v4 → v5 |
|---|---|---|---|---|
| recall@1 | — | 0.600 | 0.636 | **+0.036** |
| recall@5 | 0.927 | 0.873 | 0.909 | **+0.036** |
| recall@20 | — | 0.982 | 0.964 | −0.018 |
| MRR | — | 0.724 | 0.754 | **+0.030** |
| nDCG@10 | — | 0.779 | 0.785 | **+0.006** |
| citation accuracy@5 | 0.638 | 0.582 | 0.602 | **+0.020** |
| abstention accuracy | — | 0.500 | 0.333 | **−0.167** |
| false abstention | — | 0.036 | 0.000 | **−0.036** |

**v5 improves on v4 on every retrieval metric except recall@20.** The
regression the gate reports is real but it is v3 → v5, and most of it was
already present in v4, unrecorded.

## It is not a volume effect

v5 holds 2.7× v4's chunks, so the obvious hypothesis is dilution: more
candidates competing for five slots. The haystack analysis
(`haystack.json`) says otherwise.

| bucket | items | citation accuracy@5 | recall@5 |
|---|---|---|---|
| haystack grew ≥1.5× | 15 | **0.650** | **1.000** |
| haystack stable <1.5× | 46 | 0.507 | 0.761 |

Items facing *more* competing documents scored **better**, not worse. The new
material is helping the questions it touches. Whatever costs citation
accuracy is not corpus growth.

## What is actually worth fixing

**Abstention accuracy, 0.500 → 0.333.** Six golden-set items expect a refusal:
contract elements, tenancy deposit, noise pollution, defective goods,
workplace harassment, a Canadian student visa. v5 answers one more of them
than v4 did.

This needs splitting before it is called a defect. v5 added 288 Andhra Pradesh
documents and state law, so tenancy, workplace harassment and consumer
questions may now have genuine corpus support — in which case abstaining is no
longer the right answer and the golden set's expectation is stale. A Canadian
visa question must abstain under any corpus, and if that one changed it is a
real safety regression.

That distinction is not yet made. It requires running the six queries and
reading what comes back, which is pending.

## What was not done, deliberately

The baseline was **not** re-recorded. A `--record` here would convert an
unexamined regression into the new contract and erase the evidence that v3
ranked citations better than either successor. Re-recording is a decision to
take once the abstention split above is understood, and it belongs to the
cutover review, not to the engineer who ran the gate.
