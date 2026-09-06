# Where the project stands

*7 September 2026. Corpus `global_legal_corpus_v3`, 24,810 points, deployed.*

## State

| | |
|---|---|
| Backend tests | 956 |
| Red-team (cross-tenant) | 36, passing against v3 |
| Frontend tests | 38, one palette, both themes |
| Citizen | feature-complete |
| Police | investigation workflow complete |
| Advocate | complete except the debate room, parked |
| Admin | complete |
| Migrations | at head, verified up and down |
| Full stack | boots clean: database, Qdrant, Ollama, MPS, zero startup errors |

Three CI gates: retrieval quality, answer quality, and provision reach.

## What was actually wrong, and is now fixed

Four defects, each found by measurement rather than inspection.

**The parser could not see half the BNSS.** Both section-heading patterns
required a title after the number; the 2023 Sanhitas print titles as marginal
notes, often with no full stop. BNSS s.35 and s.173 were absent from the index
entirely. Now 100% section coverage, up from 50%.

**The abstention gate discarded verified law.** It refused on a *ratio* of
verified claims to attempted ones, so a thorough answer scored worse than a
narrow one. `child-needing-care` produced ten verified claims, ran 332
seconds across three passes, and printed "insufficient evidence". Publication
now turns on absolute sufficiency: latency p50 fell 102.6 s to 53.0 s.

**Nothing asked whether the evidence was about the question.** Verification
grades a claim against its own source; no stage asked whether the source
addresses what was asked. `noise-pollution` was answered from passages
containing neither "noise" nor "neighbouring".

**Retrieval could not reach the governing provision.** BNSS s.173 answers "how
is an FIR registered?" and contains none of those words. Recall@5 read 0.927
while the provision was absent from the top 100, because the golden set's
predicates match any passage containing a phrase -- a judgment quoting the
section satisfies the item. Following the corpus's own citations forward
through the NCRB concordance recovers it (§5.7 of the PRD).

## Known limitations, measured

1. **Provision reach is 5 of 8.** `scripts/check_provision_reach.py` records
   it and CI fails when a reachable provision stops being reachable. The three
   misses are diagnosed, not merely listed:
   - *default bail*: the passages cite CrPC ss.437 and 437A once each, below
     the corroboration floor, and those map to the BNSS bail sections rather
     than to s.187, whose proviso creates the entitlement.
   - *grounds of arrest*: the passages cite Article 22 three times. That is
     the constitutional right; BNSS s.47 is its statutory implementation. A
     right-to-implementation bridge is a different relation from a repeal
     mapping and does not exist.
   - *theft*: the retrieved judgments happen not to cite IPC ss.378 or 379.
2. **Ground coverage 0.477.** Capped by `MAX_CLAIMS = 10`; BNSS s.35(1)
   enumerates ten grounds. Raising it to 18 was measured and reverted --
   latency trebled, coverage did not move, and two working answers were lost,
   because a larger budget adds speculative claims that drag the support ratio
   under the fabrication floor.
3. **Reading grade 14.4** on a citizen surface. Statutory prose is
   polysyllabic, so any correct answer runs high, but this is not where a
   citizen surface should sit.
4. **`workplace-harassment` answers a gap.** The corpus holds the POSH
   committee-constitution advisory and not the complaint pathway, and five of
   eight passages carry "harassment" and "workplace" honestly. Right topic,
   wrong sub-topic is not a lexical problem and the sufficiency gate does not
   claim to solve it.
5. **Civil law is absent, not thin** -- see [CORPUS_GAPS.md](CORPUS_GAPS.md).
6. **The advocate evaluation slice is 7 items**, too few to tune against.

## What would be worth doing next

In descending value, and none of it urgent:

1. **A right-to-implementation bridge.** Article 22 → BNSS s.47, Article 21 →
   the bail provisions. The same shape as the concordance and the same
   deterministic character; it would close the s.47 miss and probably others.
2. **Reading level for the citizen surface.** Change one thing and measure --
   a previous prompt change took ground coverage 0.67 to 0.50.
3. **A larger advocate slice** before tuning anything for that role.
4. **The debate room**, if the 12-16 minute cost is acceptable.

## What not to do

Add features. Every module is feature-complete and the remaining problems are
quality problems with measured causes. Another surface makes them harder to
see, not easier.

Tune a threshold without measuring it first. Two of this project's three
biggest time sinks were plausible fixes shipped on reasoning rather than
evidence, both reverted.
