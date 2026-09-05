# Chunk contract v2 — build record

Measurements taken while building `global_legal_corpus_v2` alongside the live
`global_legal_corpus`, so both remain queryable and the cutover is a change to
`QDRANT_GLOBAL_COLLECTION` rather than another re-index.

## Configuration

| | |
|---|---|
| Machine | Apple M5 Pro, 18 cores, 24 GB unified, macOS 27.0 |
| Embedding | BAAI/bge-m3, 1024-d dense + learned sparse, MPS |
| Vector store | Qdrant, server-side RRF, Cosine |
| Corpus | 419 physical → 381 canonical documents |
| Re-chunk | `--rechunk`, from cached extracted text, no OCR |
| Live backend | running concurrently on :8000 (Ollama holds ~11 GB of GPU) |

## Corpus shape, v1 → v2

| | v1 | v2 |
|---|---:|---:|
| Chunks | 25,517 | 24,254 |
| Median words | 109 | 120 |
| Under 20 words | 21.9% | 19.2% |

1,263 chunks (4.9%) removed as furniture by the quality classifier.

## What the contract added

| Field | Coverage |
|---|---|
| `embed_text` | 24,254 (100%), median +24 words of Act/heading/section context |
| `cited_provisions` | 21,107 edges |
| `cited_cases` | 7,715 edges |
| chunks carrying either | 9,543 (39.3%) |

### Structural roles

| Role | Chunks | Share |
|---|---:|---:|
| provision | 12,053 | 49.7% |
| prose | 5,912 | 24.4% |
| reasoning | 3,908 | 16.1% |
| definition | 1,338 | 5.5% |
| order | 687 | 2.8% |
| arguments | 145 | 0.6% |
| facts | 128 | 0.5% |
| schedule | 50 | 0.2% |
| issues | 31 | 0.1% |
| explanation | 2 | 0.0% |

## Known limitation: sub-provision roles do not survive this chunk size

`proviso`, `explanation` and `illustration` are assigned from patterns anchored
at the start of a chunk. At 700-token chunks these almost never lead:

| Role | Chunks containing it | Leading a chunk | Labelled |
|---|---:|---:|---:|
| proviso | 1,201 | 8 | 0 |
| explanation | 558 | 1 | 2 |
| illustration | 278 | 1 | 0 |

So the field answers "what does this chunk open with", not "what is in it", and
for these three the answer is almost always "not this". A chunk of this size
contains many provisos; the role is the wrong shape for them. The roles that do
work — provision, definition, and the judgment roles driven by the parser's
`unit_kind` (reasoning, order, facts, issues, arguments) — are the ones police
and advocate routing need, so this is recorded rather than fixed here. Fixing it
means either a multi-valued "contains" field or smaller chunks, and both should
be measured against the golden set before being chosen.

`structural_role` lives in the payload, so correcting it later does not require
re-embedding.

## Defects found while building

**Gazette masthead indexed as content.** Every Gazette of India PDF opens with a
masthead whose Devanagari is ISCII rendered through a Latin font
(`jftLVªh lañ … REGISTERED NO. DL—(N)04/0007/2003—23`). These were classified
`indexed`. They sit on the first page of the most-queried Acts, and
`build_embed_text` prefixes each chunk with its Act name — so the enrichment
made the artefact *more* retrievable, not less. Rejected on three signals;
four chunks in an eight-document sample open on a masthead and run 221–700
words into the Act, and those are kept.

**hf_xet hangs before embedding starts.** The hub's Xet backend blocked
indefinitely revalidating an already-cached model rather than falling back to
the local copy. Nine minutes produced no embeddings and no error. `HF_HUB_OFFLINE=1`
is required for a native ingestion run once models are cached.

**Three kinds of state were shared between collections** — the ingestion ledger,
the chunk files, and the embedding cache. Each is now keyed by collection. The
embedding cache was the dangerous one: v1 embedded `chunk.text`, v2 embeds
`embed_text`, and a chunk id can survive a re-chunk unchanged, so a shared cache
returns a well-formed vector describing the previous contract's text.

## Embedding throughput

Measured directly over 64 real corpus chunks on an idle GPU with 16.7 GB free,
after a first attempt measured the wrong thing:

| Batch size | Chunks per minute |
|---:|---:|
| 8 | 282 |
| 16 | 245 |
| 32 | 191 |

Larger batches are slower. The encoder pads each batch to its longest member
and legal chunk lengths vary by two orders of magnitude (median 822
characters, p99 6,760, max 64,802), so a wider batch mostly buys padding. The
default stays at 8.

### The measurement that was wrong

An earlier reading put batch 32 at 503 points per minute against batch 8 at
92, and the default was raised on it. Both numbers were counted as points
appearing in the vector store, which is not a throughput measure: a document
is upserted only when it finishes, so the count sits still through a long
document and then jumps by several hundred. The "5.5x speedup" was one such
jump, and the following minute recorded zero.

Sampling a rate needs a signal that advances continuously with the work. The
corrected numbers above time the embedder itself.

The real optimisation available here is grouping chunks of similar length into
a batch. It is not taken because the embedding cache saves resumable parts by
contiguous start index, and reordering would break crash-resumability.

## Retrieval quality on the live collection, golden set v2

All hybrid (the deployed Fast lane), same collection, changes applied in order.
`wrongly declined` is the share of *answerable* questions the abstention gate
refused; without it, tightening abstention looks free.

| Change | R@1 | R@5 | MRR | nDCG@10 | abstention | wrongly declined |
|---|---:|---:|---:|---:|---:|---:|
| Baseline (golden set v1, 21 items) | 0.53 | 0.73 | 0.630 | 0.625 | 0.33 | not measured |
| Distinctive-term gate restored | 0.44 | 0.67 | 0.549 | 0.574 | 0.67 | 0.28 |
| Colloquial and inflection fixes | 0.39 | 0.67 | 0.522 | 0.554 | 0.67 | 0.00 |
| Prefer the law in force | 0.44 | 0.72 | 0.555 | 0.577 | 0.67 | 0.00 |

The first row is not directly comparable: it was measured against golden set
v1, which had 21 items, credited only the repealed Code of Criminal Procedure
on two of them, and did not measure false abstention at all. It is kept here
because it is the number that started this work.

Reading the rest: abstention doubled and stayed doubled. The dip at the second
step is the three currency items ceasing to be declined and beginning to fail
on recall instead — the same defect, recorded where it belongs. The third step
recovers it and more.

Two items are missed by every configuration, `search-of-place` and
`phone-stolen`. Both relevance phrases exist verbatim in the corpus, so these
are retrieval failures rather than bad specifications; `phone-stolen` is the
vocabulary-mismatch case the `embed_text` prefix exists to address, which is
what the v2 collection is being built to test.

Two gaps are still answered rather than declined, `consumer-complaint` and
`posh-workplace`. Both have a topical term the corpus does contain in passing
— "complaint" appears in 752 chunks — so the distinctive-term rule finds
something to require and something that satisfies it.

## Rejected: filtering garbled OCR by a wordlike-token ratio

`phone-stolen` is missed by every retrieval configuration, and inspecting what
it *does* return suggested a cause. Rank 1 was the three-word fragment
`FROM  THE  PHONE`; the e-FIR advisory — the right document — was retrieved,
but the chunk was OCR wreckage about app stores rather than the procedure. The
new quality classifier rejects the first of those and keeps the second, so the
obvious next rule was to reject chunks whose tokens mostly are not words.

Measured before implementing. Of 22,464 chunks with eight or more words, 610
(2.7%) score below a wordlike-token ratio of 0.35. But the band is not
furniture:

| structural role | below 0.35 | share of that role |
|---|---:|---:|
| provision | 436 | 4.2% |
| prose | 145 | 2.5% |
| schedule | 6 | 12.2% |
| reasoning | 15 | 0.4% |

157 of the 610 (25.7%) contain operative legal language, and the examples are
not marginal:

    7. Rights of citizenship of certain migrants to Pakistan.—Notwithstanding ...
    11. Parliament to regulate the right of citizenship by law.—Nothing in the ...

Those are Articles 7 and 11 of the Constitution. They score low because the
scanned text spaces its em-dashes and runs headings into the provision, not
because they are damaged. The rule would have deleted them silently, which is
the precise failure the classifier's own docstring is written against.

Not implemented. The remedy for `phone-stolen` is not heavier filtering — the
governing passage is not being retrieved at all, and no amount of deleting
other chunks retrieves it. It is a vocabulary gap: the citizen writes "my
phone was stolen" and the corpus writes "information relating to the
commission of a cognizable offence". That is what the `embed_text` prefix and,
beyond it, query expansion are for.

## Rejected: removing the per-batch MPS allocator flush

`_encode_batch` calls `torch.mps.empty_cache()` in a `finally`, so the
allocator is flushed after every batch of eight and not only on the error path
it was written for. With the rebuild appearing to run at roughly 57 chunks per
minute against a benchmark of 282, this looked like the missing factor.

Measured over 96 randomly sampled corpus chunks of varied length:

| | chunks/min |
|---|---:|
| with the per-batch flush | 203 |
| without it | 229 |

1.13x. Not the gap, and the flush is what keeps a long document from
exhausting MPS memory, so it stays.

The gap was mostly my own doing: the readiness-warmed backend holds BGE-M3 and
the reranker resident on the same GPU, and every evaluation run and benchmark
in this session competed with the rebuild for it. Uncontended embedding of
varied real chunks is ~203/min.

Worth stating because the sampled profile pointed the wrong way too: `sample`
showed 6,538 of ~7,000 frames inside `libBLAS`, which reads as CPU-bound work.
The model is on `mps:0` in fp16 — those frames are the CPU-side threads around
MPS dispatch, not the matmuls.

## Ablation on the live index, golden set v3 (48 items, three roles)

| config | R@1 | R@5 | R@20 | MRR | nDCG@10 | cite@5 | abstention | false abstain | ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| dense | 0.69 | 0.83 | 0.98 | 0.766 | 0.771 | 0.55 | 0.83 | 0.19 | 99 |
| sparse | 0.60 | 0.86 | 0.95 | 0.712 | 0.746 | 0.60 | 0.83 | 0.14 | 84 |
| **hybrid** (deployed) | **0.69** | 0.83 | 0.98 | 0.759 | 0.766 | 0.60 | 0.83 | 0.17 | **91** |
| reranked | 0.64 | 0.83 | 0.98 | 0.744 | 0.773 | 0.61 | 0.83 | 0.17 | **5126** |

### The cross-encoder does not earn its place

5,126 ms per query against hybrid's 91 -- **56x** -- and it buys nothing:
R@1 falls 0.69 to 0.64, R@5 and R@20 are unchanged, citation accuracy moves
0.60 to 0.61 and nDCG 0.766 to 0.773. Both of those are inside the noise this
set can resolve at 42 answerable items.

This is the second independent measurement to say so; the first, against a
different golden set, showed R@1 falling 0.53 to 0.33. Reranking is standard
practice and it is not helping here, most likely because RRF over a corpus
this homogeneous has already done the work the cross-encoder exists to do.

It is the single largest cost in the Deep lane. Removing it is worth more than
any prompt or batching change measured so far.

### Police retrieval is the weakest of the three roles

| role | items | R@5 (hybrid) | citation accuracy@5 |
|---|---:|---:|---:|
| citizen | 23 | 0.91 | 0.70 |
| police | 12 | 0.83 | **0.45** |
| advocate | 7 | 0.57 | 0.57 |

Recall is respectable for police and citation accuracy is not: barely two of
five shown passages are on-topic, against seven of ten for citizens. Police
questions -- chain of custody, seizure memos, identification parades -- pull
long procedural documents whose neighbouring passages are about something
else. The pooled 0.60 hides this completely, which is why the harness reports
per role.

Advocate R@5 of 0.57 is the lowest figure here, on only 7 items. Too few to
act on; worth widening before drawing a conclusion.

### What is still declined that should not be

False abstention is 0.17 -- seven answerable questions refused. Three are the
currency items (`theft-current-law`, `arrest-current-law`,
`evidence-current-law`), which ask which law applies *now*; the distinctive
term ends up being a word the corpus never uses. `evidence-current-law` is
missed entirely by every configuration.

Sparse alone has the lowest false abstention at 0.14 and the highest R@5 at
0.86, while being worst at R@1. That combination is worth understanding before
any fusion weighting is changed.

Abstention accuracy is 0.83 across every configuration: five of six known
corpus gaps are correctly declined, and only `workplace-harassment` is
answered.
