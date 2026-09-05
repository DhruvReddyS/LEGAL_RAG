# What to do next

Everything that could be finished without Docker running and without a quiet
machine is done and committed. Four things are blocked on you, in this order.

## 0. Start Docker, then finish the corpus rebuild

Docker Desktop is stopped, which is why the rebuild died and why the
integration and red-team suites currently skip. The rebuild is at **249 of 381
documents**, with **5 documents failed** — all five failed with
`ResponseHandlingException: All connection attempts failed`, which is Docker
going away underneath them, not a data problem.

```bash
docker compose --env-file .env -f docker/docker-compose.yml up -d --wait postgres qdrant minio
```

Then resume. It skips the 249 already done and retries the 5 that failed:

```bash
cd backend && QDRANT_GLOBAL_COLLECTION=global_legal_corpus_v2 LEGAL_KB_ROOT="$PWD/../data/legal_kb" HF_HUB_OFFLINE=1 HF_HOME="$PWD/../data/legal_kb/cache/models" ../.venv-ingest/bin/python -m app.ingestion.pipeline --rechunk --resume
```

Expect roughly 4–5 hours for the remaining ~11,000 chunks. It checkpoints
after every document, so an interruption costs one document.

**Do not run this at the same time as anything else that uses the GPU.** The
14B model, both encoders and a second copy of BGE-M3 in the ingestion process
do not fit in 24 GB together — that is what put the machine at 34 GB of swap.

## 1. Reboot, then take the clean baseline (Task 2)

Only after the rebuild finishes. Close other applications; the measurement is
worth as much as the quiet it was taken in.

```bash
.venv-ingest/bin/python scripts/measure_baseline.py
```

It refuses to pretend: if swap grows during the run it says the timings are
not a clean baseline. Output lands in `docs/evidence/baseline-<timestamp>.json`.

## 2. Run the currency migration (Task 3)

Backfills resolved currency onto all 25,517 points. Resumable, idempotent.
Dry run first — it writes nothing and tells you what would change:

```bash
.venv-ingest/bin/python scripts/migrate_currency_payload.py --dry-run
.venv-ingest/bin/python scripts/migrate_currency_payload.py
.venv-ingest/bin/python scripts/migrate_currency_payload.py --collection global_legal_corpus_v2
```

This is a payload migration on the live index. It is the one step here that
changes stored data, so it is yours to authorise rather than mine to run.

## 3. Measure v1 against v2, then decide (Task 5)

```bash
.venv-ingest/bin/python scripts/evaluate_retrieval.py \
  --configs dense sparse hybrid reranked \
  --collection global_legal_corpus --out docs/evidence/eval-v1.json

.venv-ingest/bin/python scripts/evaluate_retrieval.py \
  --configs dense sparse hybrid reranked \
  --collection global_legal_corpus_v2 --out docs/evidence/eval-v2.json
```

That is also the ablation: dense only, sparse only, hybrid without rerank, and
the full pipeline, in one pass each.

Cut over only if v2 wins on recall and citation accuracy. Not on point count,
not on latency. The cutover itself is one environment variable —
`QDRANT_GLOBAL_COLLECTION` — so a rollback is a restart.

Then record the baseline the CI gate will defend:

```bash
.venv-ingest/bin/python scripts/check_quality_gate.py --result docs/evidence/eval-v1.json --record
```

## One decision I could not make for you

The section mapping table (`data/legal_kb/metadata/section_mapping.json`) is
**model-authored and marked `pending_legal_review`**. 54 pairs across IPC/BNS,
CrPC/BNSS and IEA/BSA, with 8 flagged where the elements of the offence
changed rather than just the number.

The interface says it is unreviewed wherever it shows a mapping. It should be
checked against the official concordance before this is shown to anyone
outside the project. A wrong section mapping is the kind of error a police
user acts on immediately.
