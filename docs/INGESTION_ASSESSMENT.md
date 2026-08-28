# Final Gold corpus ingestion and RAG assessment

Final acceptance snapshot: **2026-08-25 IST**. All counts below were measured
from the local artifacts and live services. Values explicitly labelled
"estimate" or "artifact window" are not stopwatch measurements.

## Acceptance result

| Gate | Final result |
|---|---:|
| Physical PDF manifest/files | 419 / 419 |
| Canonical documents | 381 |
| Exact duplicate copies removed from compute path | 38 |
| Checkpoint | 381 complete, 0 failed |
| Extracted canonical pages | 17,426 |
| Final chunks | 25,517 |
| Valid complete embedding caches | 381 / 381 |
| Durable cached embeddings | 25,517 / 25,517 (100%) |
| Qdrant Gold points | 25,517 |
| Payload/vector validation issues | 0 |
| Strict validation issues | 0 |
| Retrieval smoke queries | 12 / 12 passed |
| Backend tests | 72 / 72 passed |
| Next.js production build | Passed; static export |
| Docker default services | PostgreSQL, Qdrant, MinIO, backend healthy |

The accepted corpus total is 25,517 rather than the earlier 25,518 because one
punctuation-only `:` chunk was correctly removed. Its Qdrant point, local chunk,
checkpoint count, and embedding-cache entry were reconciled. The affected
18-page OCR artifact was independently regenerated in the Tesseract-enabled
backend container; its 21 regenerated chunk IDs and texts matched the repaired
chunks exactly.

## Corpus quantity

| Metric | Physical/source view | Canonical/compute view |
|---|---:|---:|
| Documents | 419 | 381 |
| PDF bytes | 691,556,372 (659.52 MiB) | 641,658,344 (611.93 MiB) |
| Pages | 19,632 | 17,426 |
| Duplicate overhead | 38 copies | excluded from OCR/embedding |

Every source record retains checksum, source URL/provenance, official-source
verification, and physical-to-canonical mapping. Canonicalization saves about
49.90 MB of duplicate PDF compute input.

Canonical documents and chunks by normalized legal type:

| Type | Documents | Chunks |
|---|---:|---:|
| Act | 82 | 7,421 |
| Rule | 41 | 3,907 |
| Government guidance | 110 | 1,437 |
| Police manual | 18 | 954 |
| Supreme Court judgment | 79 | 7,124 |
| High Court judgment | 14 | 210 |
| Law Commission report | 24 | 1,581 |
| Constitution | 1 | 2,434 |
| Order | 4 | 259 |
| Notification | 5 | 45 |
| Government handbook | 2 | 108 |
| Amendment | 1 | 37 |

## Extraction and OCR

| Metric | Result |
|---|---:|
| Canonical documents extracted | 381 / 381 |
| Pages represented | 17,426 / 17,426 |
| Native PyMuPDF pages | 13,448 (77.17%) |
| Tesseract-selected OCR pages | 3,978 (22.83%) |
| Documents using OCR | 100 / 381 (26.25%) |
| Extraction warning records | 4,025 |
| Extracted JSON storage | 77,870,633 bytes (74.26 MiB) |

OCR is attempted when native extraction produces fewer than 40 characters and
is selected only when it improves the text. Warnings therefore include expected
low-native-text and OCR quality signals; they are not document failures.

The initial extracted-artifact timestamps span **1 h 09 m 17 s**, from
2026-08-20 23:32:38 to 2026-08-21 00:41:55 IST. This is an artifact-production
window for extraction + OCR + structural parsing + chunk writing, not a pure
stage benchmark. The original run did not persist per-stage timers, so exact
standalone extraction, OCR, and chunking times cannot honestly be recovered.

## Chunking

The chunker preserves legal structure and uses a fallback ceiling of 700
whitespace-delimited word units with an 80-unit overlap. These are not BGE
tokenizer tokens.

| Metric | Result |
|---|---:|
| Total chunks | 25,517 |
| Average chunks/document | 66.97 |
| Total Unicode characters | 41,062,887 |
| Total whitespace words | 6,021,060 |
| Words/chunk minimum | 1 |
| Words/chunk median | 111 |
| Words/chunk mean | 235.96 |
| Words/chunk p75 | 411 |
| Words/chunk p90 / p95 / maximum | 700 / 700 / 700 |
| Chunk JSONL storage | 67,865,517 bytes (64.72 MiB) |

Tokenizer-dependent volume is approximately **8.01–10.27 million tokens**:
6,021,060 words × 1.33 gives 8,008,010; 41,062,887 characters ÷ 4 gives
10,265,722. This range is an estimate and includes deliberate overlap.

## Embeddings and vector database

| Metric | Result |
|---|---:|
| Model | BAAI/bge-m3 |
| Dense dimension | 1,024 |
| Sparse representation | learned lexical weights |
| Embeddings | 25,517 dense + 25,517 sparse |
| Complete valid document caches | 381 |
| Invalid complete/part caches | 0 / 0 |
| Durable gzip embedding cache | 194,659,528 bytes (185.64 MiB) |
| Dense float32 lower bound | 104,517,632 bytes (99.68 MiB) |
| Unique local model cache | 6,876,300,323 bytes (6.40 GiB) |
| Qdrant Gold logical points | 25,517 |
| Qdrant Docker volume | about 3.484 GB |

The Qdrant volume includes all three collections plus payloads, sparse vectors,
HNSW indexes, WAL/segments, and historical replacement overhead, so it is not a
Gold-only vector-size measurement.

The first-to-last original completion timestamps for the 380 unaffected
documents span **22 h 50 m 26 s**. That wall envelope includes stops, retries,
failed experiments, and idle time. It is not active GPU time. A measured stable
MPS window processed **505 chunks in 193.48 s = 156.6 chunks/min**. At that rate,
25,517 chunks represent about **2 h 43 m of active optimized embedding work**.
Both measurements are retained because they answer different questions:

- 22 h 50 m: observed project wall envelope with interruptions;
- ~2 h 43 m: throughput-derived active optimized estimate;
- exact cumulative active embedding time: unavailable because original
  per-batch timing telemetry was not recorded.

One Apple MPS worker with batch size 16 was the accepted safe configuration.
Concurrent MPS/CPU writers were rejected after they increased contention and,
before locking improvements, risked checkpoint overwrite. Checkpoint writes now
use file locking, atomic merge, unique temporary files, document claims, and
resumable per-batch parts.

## Retrieval and multi-agent metrics

The 12-query legal smoke suite passed for mandatory FIR registration, arrest
safeguards, anticipatory/default bail, FIR quashing, electronic evidence,
POCSO, NDPS, IPC→BNS, CrPC→BNSS, Evidence Act→BSA, and constitutional privacy.
Each accepted result is Gold-only, officially verified, page-cited, and has a
finite fused/reranker score plus at least one valid retrieval-modality score.

Live end-to-end acceptance query:

| Metric | Result |
|---|---:|
| Query | When is registration of an FIR mandatory in India? |
| Pipeline | query understanding → retrieval → reasoning → verification → response |
| Wall time | 47.18 s |
| Verification confidence | 0.625 |
| Evidence badge | Moderate |
| Verified citations returned | 2 |
| Retry count | 0 |

An earlier deliberately observed 40K-context/default-thinking run took 183.62 s
and still refused the answer. Switching to the installed 16K Qwen profile,
disabling hidden thinking, bounding output to 900 tokens, and fixing
claim/citation parsing reduced accepted-query latency by **74.3%**. The graph
still retries retrieval at confidence below 0.5 and stops after two retries.

## Application and infrastructure footprint

| Item | Measured size/result |
|---|---:|
| Frontend static `out/` | 743,726 bytes (~726 KiB) |
| Frontend first-load JS | 100 kB |
| Frontend dependencies | ~286 MiB unique files (`du`: ~332 MiB allocated) |
| Backend Docker image | 2.49 GB |
| PostgreSQL volume | 49.36 MB |
| Qdrant volume | 3.484 GB |
| MinIO volume (empty test buckets) | 88.88 kB |

The frontend is Next.js 14.2.35 + React 18 + Tailwind + shadcn conventions,
exports statically, uses the server-persisted `/chat/query` API, and never writes
JWTs to `localStorage`. Web auth uses HttpOnly access/refresh cookies. Tauri v2
source/config is scaffolded.

## Reproduce acceptance

From the repository root:

```bash
docker compose --env-file .env -f docker/docker-compose.yml up -d --build
docker compose --env-file .env -f docker/docker-compose.yml ps
curl --fail http://localhost:8000/health

QDRANT_URL=http://localhost:6333 LEGAL_KB_ROOT="$PWD/data/legal_kb" \
  PYTHONPATH="$PWD/backend" .venv-ingest/bin/python \
  -m app.ingestion.validate --require-complete

python3 scripts/ingestion_progress.py

QDRANT_URL=http://localhost:6333 LEGAL_KB_ROOT="$PWD/data/legal_kb" \
  HF_HOME="$PWD/data/legal_kb/cache/models" HF_HUB_OFFLINE=1 \
  TRANSFORMERS_OFFLINE=1 PYTHONPATH="$PWD/backend" EMBEDDING_DEVICE=auto \
  .venv-ingest/bin/python -m app.ingestion.retrieval_smoke

cd frontend
npm install
npm run build
python3 -m http.server 3000 --directory out
```

For host-side integration tests, load `.env` privately and override Docker
service hostnames to localhost as shown in `docs/PROJECT_HANDOFF.md`. Never
print or commit `.env`.

## Remaining manual prerequisite

Web and backend execution require no additional manual coding. Native Tauri
packaging is blocked only by the machine toolchain: Xcode Command Line Tools are
installed, but Rust/rustup/Cargo are not. Install Rust from
<https://rustup.rs/>, restart the terminal, then run:

```bash
cd frontend
rustc --version
cargo --version
npm run tauri build
```

Full Xcode is reported absent by `tauri info`; install it only if macOS signing,
App Store distribution, or the local Tauri build explicitly requests it.
