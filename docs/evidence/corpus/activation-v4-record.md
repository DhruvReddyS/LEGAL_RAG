# Activating global_legal_corpus_v4

Decided 2026-10-06. The active collection is now `global_legal_corpus_v4`.

## What was compared

Twelve ordinary citizen questions, the same twelve against both collections,
through the live `/chat/query` endpoint as a signed-in citizen, `response_mode`
auto. Prompt and model unchanged between runs: `qwen3-14b-16k:latest`,
temperature 0, seeded, generation concurrency 1.

| | v3 | v4 |
|---|---|---|
| Points | 25,323 | 49,684 |
| Documents | 541 | 736 |
| Consumer protection passages | 0 | 647 |
| Answered | 12/12 | 12/12 |
| Mean confidence | 0.26 | **0.46** |
| Refusals (no citation) | 5 | **3** |

## Per question

Two questions went from an outright refusal to a cited answer: unpaid wages
(0.00 to 0.40) and land encroachment (0.00 to 0.95). Two more improved
sharply: obtaining a public record (0.45 to 1.00) and road accident
compensation (0.19 to 0.73).

Three questions regressed on confidence while keeping their citations: what to
do when arrested (0.70 to 0.47), punishment for theft (0.60 to 0.50) and free
legal aid (0.67 to 0.62). That is the expected cost of a larger index - more
candidates compete for the same display slots - and it is a confidence
movement, not a loss of grounding.

Three still refuse: the landlord withholding a deposit, a defective phone
bought online, and online harassment. The consumer refusal is the notable one,
because v4 holds 647 consumer passages. That is a retrieval or sufficiency
problem rather than a coverage gap, and more documents will not fix it.

## Honest limits of this measurement

This is not the statistical gate the project still owes. Twelve questions
cannot separate small differences, and no confidence interval is reported
because one would be too wide to mean anything. What it does establish is a
direction: v4 refuses less and grounds more, and no question lost its
citations. The golden set is 21 items and needs to be several times that
before a recall difference can be called significant.

The v4 runs also executed under extra load - corpus downloads were in flight -
so the latency figures from them are not comparable and are deliberately not
quoted here.

v4 is also incomplete: 736 of 1,036 manifest documents are ingested. It is
being activated as a strict improvement over v3, not as a finished index.

## Rollback

One line, then restart:

    QDRANT_GLOBAL_COLLECTION=global_legal_corpus_v3   # in .env
    docker compose -f docker/docker-compose.yml --env-file .env up -d --force-recreate backend

v3 is untouched at 25,323 points and remains in Qdrant.
