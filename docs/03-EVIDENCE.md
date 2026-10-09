# 03 — Evidence

*How Corpusil is measured, what each release must pass, and what is still
wrong. A number here always states what it was measured against and when.*

---

## 1. Evaluation

Two separate questions, measured separately, because the answer to the first
tells you nothing about the second: **does retrieval find the right law**, and
**is the answer any good**.

### 1.1 Golden set

`data/legal_kb/evaluation/golden_set_v3.json` — 61 items: 29 citizen, 25 police,
7 advocate; 55 answerable and 6 expected abstentions.

Design constraints:

- **Relevance never pins to a chunk ID.** Chunk IDs are content-addressed and
  change on every re-chunk, which is exactly when the set is needed. Items name
  an Act, a section, or a distinctive phrase.
- **Drawn from classes the heuristics were never tuned against**, because
  scoring the cases a heuristic was written for measures the heuristic.
- **Every answerable item was verified against the corpus first**, so a miss is a
  retrieval failure and not an unwinnable item.
- **False abstention is scored**, because tightening the gate looks free
  otherwise.
- **45 ground expectations across 10 answering items**, each authored by reading
  the Act out of this corpus — BNSS ss.35, 43, 47, 187, 482; BSA s.26; BNS
  s.303 — and each recording `grounds_source`. Authoring expectations from what
  the system already says is how an evaluation certifies its own subject.

### 1.2 Retrieval metrics

Recall@1/5/20 · MRR · nDCG@10 · **citation accuracy@5** · abstention accuracy ·
false abstention rate · latency — each reported **per role as well as pooled**,
because a pooled average lets one audience rot behind another.

Citation accuracy is separate from recall on purpose: recall asks whether the
governing authority came back anywhere, citation accuracy asks what fraction of
what the reader is *shown* is correct.

> **What recall does not measure, and this took months to notice.** Relevance
> predicates match any passage *containing* a phrase, so a judgment quoting
> BNSS s.173 satisfies the FIR item while the section itself is absent from the
> top 100. Recall@5 read 0.927 while the governing provision could not be
> reached for four of six core questions ([02-ARCHITECTURE](02-ARCHITECTURE.md) §4.7). A recall metric over
> phrase-matching predicates measures topical coverage, not authority. The
> per-question provision check in [02-ARCHITECTURE](02-ARCHITECTURE.md) §4.7 is the instrument that found it, and
> nothing in the golden set replaces it.

### 1.3 Answer metrics (`app/evaluation/answer_quality.py`)

Retrieval finding the law is necessary and not sufficient. A change can leave
retrieval untouched and still take ground coverage from 0.67 to 0.50 by altering
a prompt — which happened here, with the retrieval gate green throughout.

| metric | asks |
|---|---|
| unsupported claim rate | did any published claim cite evidence that was never retrieved |
| abstention correctness | did it refuse exactly when it should have |
| ground coverage | what fraction of the statutory grounds did it name |
| currency correctness | did it disclose what the resolver says it must |
| reading grade | can the intended reader read it |

They are deliberately **not averaged into one score**. An answer that reads well
and cites a repealed section is not "70% good"; it is wrong in one specific way,
and a composite hides which.

Three properties of the aggregation, each because the alternative moves the
number for a reason that is not an improvement: an item with no authored grounds
is excluded rather than scored 1.0 or 0.0; unsupported claims are summed, never
averaged, because a rule admits no rate; and currency is scored only on items
that owed a disclosure.

### 1.4 Recorded baselines and the CI gates

| baseline | value |
|---|---|
| recall@5 | 0.927 |
| citation accuracy@5 | 0.638 |
| abstention correctness | 0.836 |
| ground coverage | 0.474 (7 scored items) |
| currency correctness | 0.632 |
| unsupported claims | **0** |
| latency p50 | 53.0 s |

`check_quality_gate.py` guards retrieval at ±0.02. `check_answer_gate.py` guards
the answer metrics at ±0.05 — wider, because generation is sampled — and treats
unsupported claims as **a rule, not a metric**: no tolerance reaches it, and it
cannot be recorded into a baseline, because a baseline containing a violation
makes the next one show as no change.

Every result records the collection, golden set, embedding and generation
models, sampling settings and all six prompt fingerprints. Temperature is 0.0
and no seed is set; the record says `seeded: false` and `decoding: greedy`
rather than leaving the field null, because "no seed was set" and "the field was
not read" must not look the same.

### 1.5 Three CI groups

| Group | Asks |
|---|---|
| **Correctness** | Does the code do what it was told? (956 tests) |
| **Security** | Can a caller reach another tenant's evidence? (36 tests, plus a structural check that every `{case_id}` route enforces ownership) |
| **Quality** | Does retrieval find the right law, and is the answer any good? (61 golden items, both gates) |

---

---

## 2. Known limitations

Each is measured, and each has a stated direction rather than a shrug. Measured
6 September 2026 against `global_legal_corpus_v3`.

1. **Ground coverage is 0.474.** Answers that do publish name under half the
   statutory grounds. On `arrest-current-law` the answer names six of the ten
   grounds in BNSS s.35(1) and misses *proclaimed offender* and *stolen
   property* — **both of which were retrieved**. So this is reasoning dropping
   evidence, not retrieval failing to find it, and it is the next thing to fix.
2. **Latency p50 is 102.6 s**, against a 90 s target. The publication gate change
   should reduce it — a broad question no longer retries twice before being
   discarded — but that is a prediction, not a measurement.
3. **Statutory vocabulary still limits retrieval, though less.** Following
   citations ([02-ARCHITECTURE](02-ARCHITECTURE.md) §4.7) recovers the governing provision for the FIR,
   anticipatory-bail and dying-declaration questions, which retrieval could
   not reach at all. Two known misses remain: default bail, where the
   passages cite CrPC ss.437 and 437A and so lead to the BNSS bail sections
   rather than to s.187, and theft, where the retrieved judgments happen not
   to cite IPC ss.378 or 379. Both are the same shape -- following citations
   reaches what the sources rely on, which is not always what the question
   needs -- and neither is fixed by ranking.
4. **Reading grade is 14.4** across all roles, 14.1 for citizens. That is
   undergraduate level for an audience that includes people with no legal
   training. Statutory prose is polysyllabic by nature, so the figure runs high
   for any correct answer, but it is not where a citizen surface should sit.
5. **One corpus gap is still answered.** `noise-pollution` produces an answer
   where the corpus has nothing — the only failure in the dangerous direction,
   and worth more than the eight in the safe one.
6. **60% of chunks have unverified currency.** Honestly labelled, not assumed.
   Most of the uncovered mass is judgments and Law Commission reports, for which
   "unverified" is the correct answer; there are **zero** uncurated statutory
   instruments.
7. **`is_current` is false corpus-wide** by design: every manifest row's status
   ends in "verify", and an unverified status must not be asserted as current.
8. **Civil law is absent, not thin.** The corpus is 63% criminal law and holds
   zero Acts for contract, tenancy, consumer protection or environmental
   nuisance. The system abstains correctly on all of them; see
   [02-ARCHITECTURE](02-ARCHITECTURE.md) §2.2 for what closing them would cost and why
   three of the four hosts are currently unreachable.
9. **The advocate evaluation slice is 7 items** — too few to tune against, and
   its abstention correctness of 0.71 rests on two failures.
10. **There is no v2 answer-quality run**, so the answer baseline is a baseline
    and not a comparison: none of it can be attributed to v3 rather than to the
    pipeline.
11. **The debate room would take 12–16 minutes** at roughly 25 sequential model
    calls. Deliberately parked.
12. **Sub-provision structural roles never populate**: chunks containing a
    proviso are not labelled one, because the patterns anchor at chunk start and
    a 700-token chunk holds many.

---
