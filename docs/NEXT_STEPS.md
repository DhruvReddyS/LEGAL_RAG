# Where the project stands

*Written 6 September 2026, mid-rebuild. Superseded whenever the numbers below
are re-measured.*

## The short answer

The **citizen module is feature-complete and its quality is unverified**.
Every planned citizen feature is built and 719 tests pass, but the corpus
index is being rebuilt after a parser fix that materially changes what is in
it, and no answer-quality number measured before that rebuild is worth
quoting. The police and advocate modules have their foundations plus, as of
today, the first police feature.

## What is blocking, and it is only one thing

The v3 rebuild is at **149 of 381 documents**. It must finish before any
answer number means anything.

The reason is worth stating plainly, because it is the largest single defect
found in this project. Both section-heading patterns required a title after
the section number. The 2023 Sanhitas print their titles as *marginal notes*
in a narrow left column, often with no full stop. So the parser did not see
them, and:

- **BNSS s.35 and s.173 were absent from the index entirely.** s.35 governs
  arrest without warrant; s.173 is the FIR provision, the most-asked question
  in this corpus.
- The four BNSS chunks containing "arrest without warrant" were labelled
  `section='476'`, `''`, `'46'` and `'57'` — CrPC numbers attached to BNSS
  text.
- Deep was answering questions about arrest without ever retrieving the
  provision that authorises it.

Section coverage after the fix, against the official section counts:

| act | parsed | official | coverage | was |
|---|---:|---:|---:|---|
| BNSS | 530 | 531 | 100% | 50% |
| BNS | 344 | 358 | 96% | 77% |
| BSA | 168 | 170 | 99% | 85% |
| IPC | 477 | 511 | 93% | — |
| Constitution | 457 | 395 | 116% | — |

The Constitution's 116% is legitimate: 378 plain articles with none numbered
above 395, plus 79 genuine lettered articles (21A, 124A, 239A).

## What you can test right now

Everything except answer quality. The stack runs, the API serves, and the
citizen and admin surfaces work against the v2 index.

```bash
docker compose --env-file .env -f docker/docker-compose.yml up -d --wait postgres qdrant minio
```

```bash
cd backend && ../.venv-ingest/bin/python -m pytest tests/ -q --ignore=tests/redteam
```

Note that the rebuild is writing to `global_legal_corpus_v3` while the
application still reads `global_legal_corpus_v2`, so testing now does not
disturb it and does not see the fix either.

## Features, by role

### Citizen — built
Plain-language answers with citations · Fast and Deep lanes · emergency and
refusal screening · abstention on corpus gaps · repeal and currency labelling
· source inspector · document upload and analysis · feedback · session
history · follow-up questions now routed to the lane that can resolve them.

### Citizen — not built
Rights explainer (C-04) · forum router (C-05) · drafting beyond FIR facts
(C-06) · multilingual (C-07) · upload redaction (C-02).

### Police — foundation, plus the first feature
Case creation and evidence upload · private case corpus with proven isolation
· FIR fact extraction and drafting agent · role profile and specialist
prompts · **statutory investigation timeline** (nine BNSS deadlines,
`POST /cases/{case_id}/investigation/timeline`).

The rest of the investigation workflow is unstarted.

### Advocate — foundation only
Case corpus · defence strategy agent with adverse arguments · authority
mapping. The debate room is unstarted and you have parked it deliberately.

### Admin — built
User management · corpus statistics · ingestion progress · audit log, and it
cannot reach private case material through a general search.

## Measurement, now that there is some

Before today the only instrument was retrieval recall, which says the right
passage came back and nothing about whether the answer used it. There are now
five answer-quality metrics — abstention correctness, unsupported-claim rate,
currency correctness, ground coverage and reading grade — with 45 ground
expectations authored by reading BNSS ss.35, 43, 47, 187, 482, BSA s.26 and
BNS s.303 out of this corpus.

```bash
python scripts/evaluate_answers.py --label v3
```

Both gates run in the CI quality group. The answer gate treats unsupported
claims as a rule rather than a metric: no tolerance reaches it, and it cannot
be recorded into a baseline.

## Waiting on you

1. **The five corpus gaps** — see [CORPUS_GAPS.md](CORPUS_GAPS.md). Which, if
   any, to ingest, and for tenancy, which State. Doing none is a legitimate
   choice: the system abstains correctly on all five today and the golden set
   expects it, so leaving them costs zero measured score.
2. **A schema migration for the investigation timeline.** The endpoint is
   stateless because `Case` carries no offence or date fields. Persisting them
   needs a migration, and you asked to approve those.
3. **The official MHA concordance tables.** The 54 section mappings are still
   model-authored. You ruled out human review of them, correctly — a reviewer
   approves most and misses the wrong one — and no authoritative offline
   source has been obtained.

## After the rebuild, in order

1. Measure v3 against v2 on golden set v3; `evidence-current-law`,
   `theft-current-law` and `arrest-current-law` should move.
2. Record the answer-quality baseline.
3. Re-measure the cross-encoder cost on a quiet machine — the 5,126 ms figure
   was taken while the machine was swapping.
4. Session-scoped evidence pool, so an elaboration does not re-retrieve.
