# v5 cutover — where it stands and who does what

*Paused 10 October 2026. The corpus is built and safe; the gate run was
stopped part-way to rest the machine and is fully re-runnable.*

## State

| | |
|---|---|
| `global_legal_corpus_v5` | **133,857 points, status green** |
| Documents | 1,563 of 1,563 canonical, **0 failed** |
| Doubled-text chunks | **0** (was 61) |
| Citation-furniture chunks | **0** (353 pruned after review) |
| Serving | `global_legal_corpus_v4` — unchanged, v5 is not live |

Nothing is running: no ingestion, no backend, no containers, no sleep holds.

## Gate results so far

| # | Gate | Result |
|---|---|---|
| 1 | payload / currency | **PASSED** |
| 2 | retrieval quality | **FAILED** — analysed, see below |
| 3 | answers | stopped at 8 of 61 (all `unsup 0`) |
| 4 | provision reach | not run |
| 5 | retrieval health | not run |
| 6 | latency | not run |
| 7 | provision drift | not run — never yet run against a live index |

Gate 2's failure is explained in `RETRIEVAL_GATE_ANALYSIS.md`. In short: the
recorded baseline is **v3, from 6 September**, so the gate compares v5 against
a corpus two generations old. Against v4, v5 improves on every retrieval
metric except recall@20. It is also not a volume effect — items whose haystack
grew scored *better* (0.650 citation accuracy) than stable ones (0.507).

**The baseline has not been re-recorded, deliberately.**

## Claude — backend, retrieval, answer quality

1. **Re-run the gate suite** from gate 3. Needs an idle machine on mains power;
   the latency gate is a measurement and a throttling host invalidates it.
   ```
   LEGAL_RAG_BENCHMARK_PASSWORD=... ./scripts/run_corpus_gates.sh global_legal_corpus_v5 v5-cutover
   ```
2. **Resolve the abstention regression** (0.500 → 0.333). Six items expect a
   refusal. Split them: tenancy, workplace harassment and consumer goods may
   now have real support from the 288 new Andhra Pradesh documents, which makes
   the golden set stale rather than the system wrong. A Canadian student visa
   must abstain under any corpus — if that is the one that changed, it is a
   safety defect and takes priority over everything else here.
3. **Analyse every remaining failure** against v4 rather than the v3 baseline,
   with volume separated from ranking.
4. **Fix the stale measurement itself** — `CORP-07`, golden set v4. Its
   predicates match phrases, not documents, and its 61 items barely touch the
   826 documents added since v3. Every retrieval number is softer than it looks
   until this is done.
5. **Profile ingestion memory** — the build ran on CPU for most of 43 hours
   because MPS kept running out of memory on a machine with 24 GB. Five
   hypotheses were tested and disproved (max_length, cache release, a leak,
   thread count, Docker allocation — the last was real and gave 1.8×). The
   remaining ~9 GB of compressed memory is unexplained and needs per-stage
   profiling on an idle machine.
6. **Fix the keeper's process guard** — `rebuild_until_done.sh` skips starting
   a worker when `pgrep -f "app.ingestion.pipeline"` matches anything, so a
   monitoring command containing that string stalls the build. It cannot be
   edited while the keeper is running, which is why it is still open.

## Codex — corpus, metadata, verification, release evidence

1. **Review this cutover** and the evidence in this directory. The cutover
   decision is yours; Claude has not promoted v5.
2. **Decide on re-recording the baseline.** It currently pins v3. Re-recording
   to v5 is defensible — v5 beats v4 everywhere that matters — but it would
   erase the evidence that v3 ranked citations better than either successor,
   so the commit must say why the new number is the right one.
3. **Confirm the OCR re-ingestion** of five documents: Child Helpline SOP,
   NALSA community mediation SOP, victim care scheme, Child Marriage State
   rules, Maternity Benefit (Mines and Circus) rules. Their text layers were
   doubled and unsearchable; they were re-read with OCR and two gained
   substantial content (15 → 43 and 144 → 160 chunks). Worth a spot-check that
   the OCR text is faithful.
4. **Corpus breadth** — `CORP-01`, `CORP-02`, `CORP-03` in `docs/06-PLAN.md`.
   93 judgments and two states is the ceiling on four advocate features.
   Licensing review comes before acquisition.
5. **Repoint the stale links** in `docs/evidence/**` and
   `docs/architecture/*.{json,html}`. They reference `NEXT_STEPS.md`,
   `CORPUS_GAPS.md` and `OPERATIONS.md`, which were consolidated into the six
   numbered documents. Left alone because those files are Codex's and were
   modified in the working tree.

## Needs the product owner

| Decision | Blocks |
|---|---|
| Re-record the retrieval baseline to v5? | gate 2 passing |
| Cutover v5 → serving | v1 release |
| Acquire judgment and overruling data | `A-06`…`A-09` |
| Which states the product claims to serve | `CORP-02` |

## To resume

```
cd "<repo>" && ./scripts/rebuild_until_done.sh status global_legal_corpus_v5   # should say nothing running
docker compose --env-file .env -f docker/docker-compose.yml up -d --wait postgres qdrant minio
```
Then re-run the gate suite. Do not start the containerised backend — it holds
port 8000 and is built on CPU-only torch, which makes the latency gate measure
the wrong thing.
