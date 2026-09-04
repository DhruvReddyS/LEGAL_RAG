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
