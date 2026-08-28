# Project handoff and operations runbook

Last verified: **2026-08-27 IST**. Run commands from:

```bash
cd "/Users/sripathidhruvreddy/Documents/MAJOR PROJECT"
```

## Accepted implementation

- Tier 0 infrastructure is complete: monorepo, Compose health checks, async
  SQLAlchemy/Alembic, three Qdrant collections, MinIO storage, JWT/RBAC,
  ownership checks, and audit foundations.
- Gold ingestion is complete and strictly valid: 419 physical PDFs, 381
  canonical documents, 17,426 pages, 25,517 chunks/embeddings/Qdrant points,
  381 valid caches, zero failed documents, and zero validation issues.
- Hybrid retrieval is accepted: BGE-M3 dense + learned sparse, Qdrant RRF, BGE
  reranker, and 12/12 legal smoke queries passing.
- Tier 1 multi-agent backend is implemented: LangGraph query understanding,
  retrieval, cited reasoning, claim verification, at most two retries, evidence
  badges, session memory, PostgreSQL chat persistence, ownership, and full trace
  auditing.
- Citizen frontend is implemented on the locked web stack: Next.js 14 static
  export, Tailwind, shadcn conventions, verified citation panels, secure
  HttpOnly-cookie auth, and no JWT/localStorage storage.
- The first Tier 2 professional slice is accepted: police/advocate case CRUD,
  dependency-enforced ownership, S3 evidence upload, PDF/text extraction with
  OCR fallback, private role-specific Qdrant indexing, selected/all-case search,
  immutable grounded FIR drafts, and verified advocate defence analysis.
- The frontend is an enterprise legal-operations console rather than a generic
  chatbot. Citizen, police and advocate accounts receive distinct command
  centres, navigation, specialist-agent suites, workflows, terminology,
  evidence classifications, professional workspaces and keyboard commands.
  The production static export passes; all three authenticated experiences
  passed browser QA, and the final advocate console check had no warnings/errors.
- The administrator control plane is accepted: citizen-only public registration,
  police/advocate account creation and suspension, immediate inactive-session
  enforcement, governed PDF staging/validation/publication into a searchable
  verified-extended tier, immutable Gold validation, and audit-event visibility.
- Fast Research mode is live. It returns a non-generative Gold evidence brief or
  safe abstention, skips the cross-encoder/LLM chain, exposes stage timings, and
  is selected separately from Deep Review in the UI. Startup model warm-up
  moved the 7.62-second cold load before readiness; five distinct live queries
  measured p95 448.99 ms and 100% met the five-second target at concurrency 1.
- Tauri v2 native packaging is accepted. The signed local Apple Silicon build
  produced a 9.6 MB `.app` and 2.8 MB `.dmg`; the native process, CSP/API route,
  Tauri CORS origin and four-role cookie sessions were verified.
- The P2 Document Analyzer and Source Provenance/Evidence Inspector are accepted:
  owned indexed-document review, chunk-grounded clauses/risks, corpus rejection
  of invented sections, seven-field provenance drawer, role UI and a 46.25-second
  live local Ollama run. The backend regression is now 105 tests.

Detailed final quantities, timing qualifications, storage, and throughput are
in [INGESTION_ASSESSMENT.md](INGESTION_ASSESSMENT.md). Tier 2 security and live
scenario results are in [TIER2_ACCEPTANCE.md](TIER2_ACCEPTANCE.md). The ordered
five-second Fast-mode, production scaling, and controlled global-corpus growth
work is in [PERFORMANCE_AND_CORPUS_SCALING_PLAN.md](PERFORMANCE_AND_CORPUS_SCALING_PLAN.md).
Measured Fast-mode acceptance and the remaining performance backlog are in
[FAST_MODE_ACCEPTANCE.md](FAST_MODE_ACCEPTANCE.md).
Administrator bootstrap, controls and corpus-governance acceptance are in
[ADMIN_CONTROL_PLANE_ACCEPTANCE.md](ADMIN_CONTROL_PLANE_ACCEPTANCE.md).
Native build, one-command launch, RBAC and distribution qualification are in
[TAURI_DESKTOP_ACCEPTANCE.md](TAURI_DESKTOP_ACCEPTANCE.md).
Document analysis, provenance, grounding and live acceptance are in
[DOCUMENT_ANALYZER_ACCEPTANCE.md](DOCUMENT_ANALYZER_ACCEPTANCE.md).

## Start the working system

Docker Desktop and host Ollama must be running. The installed default model is
`qwen3-14b-16k:latest`.

```bash
docker compose --env-file .env -f docker/docker-compose.yml up -d --build
docker compose --env-file .env -f docker/docker-compose.yml ps
curl --fail http://localhost:8000/health
ollama list
```

The backend entrypoint applies migrations and initializes Qdrant/storage before
starting Uvicorn. API docs: <http://localhost:8000/docs>.

Start the frontend:

```bash
cd frontend
npm install
npm run build
python3 -m http.server 3000 --directory out
```

Open <http://localhost:3000>. Register a citizen account, then ask a legal
question. The first query after process/model cold start is slower because BGE
models must load. The accepted warm-model FIR workflow took 47.18 seconds.

For the native application, the smooth local path is:

```bash
./scripts/start_desktop.sh
```

## Verify corpus and retrieval

```bash
python3 scripts/ingestion_progress.py

QDRANT_URL=http://localhost:6333 LEGAL_KB_ROOT="$PWD/data/legal_kb" \
  PYTHONPATH="$PWD/backend" .venv-ingest/bin/python \
  -m app.ingestion.validate --require-complete

QDRANT_URL=http://localhost:6333 LEGAL_KB_ROOT="$PWD/data/legal_kb" \
  HF_HOME="$PWD/data/legal_kb/cache/models" HF_HUB_OFFLINE=1 \
  TRANSFORMERS_OFFLINE=1 PYTHONPATH="$PWD/backend" EMBEDDING_DEVICE=auto \
  .venv-ingest/bin/python -m app.ingestion.retrieval_smoke
```

Expected: progress 100%, 381 complete caches, 25,517 embedded chunks, no
invalid caches; strict validation exits zero with 25,517 Qdrant Gold points;
retrieval report says overall PASS.

## Run tests

Host integration tests need `.env` secrets but Docker service hostnames must be
overridden to localhost. This command does not print secrets:

```bash
set -a
source .env
set +a
export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT:-5432}/${POSTGRES_DB}"
export S3_ENDPOINT_URL="http://localhost:${MINIO_API_PORT:-9000}"
export S3_PUBLIC_ENDPOINT_URL="$S3_ENDPOINT_URL"
export QDRANT_URL="http://localhost:${QDRANT_HTTP_PORT:-6333}"
PYTHONPATH="$PWD/backend" .venv-ingest/bin/python -m pytest -q backend/tests

cd frontend
npm run build
```

Accepted result: **105 backend tests passed** and the Next.js 14 static export
completed successfully.

## Configuration and secrets

Never print or commit `.env`. For a fresh checkout only:

```bash
test -f .env || cp .env.example .env
```

Manually provide strong, independent values for `POSTGRES_PASSWORD`,
`JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`, `S3_ACCESS_KEY_ID`, and
`S3_SECRET_ACCESS_KEY`. Keep `OLLAMA_MODEL=qwen3-14b-16k:latest` on this 24 GB
Apple Silicon machine unless a controlled benchmark supports a larger profile.

## Tauri packaging

Rust 1.98.0 and Cargo 1.98.0 are installed for the current user. Rebuild with:

```bash
cd frontend
rustc --version
cargo --version
npm run tauri info
npm run desktop:build
```

The local ad-hoc signature is valid for this capstone machine. External macOS
distribution still requires a Developer ID certificate and Apple notarization;
those credentials are the remaining manual step.

## Remaining product backlog

Continue Tier 2 in this order:

1. Legal Document Studio editing plus PDF/DOCX export.
2. Judgment summarizer and judgment similarity mode.
3. Amendment/current-law tracker and outdated-law demo. This is urgent because
   all 25,517 existing Gold payloads currently have conservative
   `is_current=false` pending official consolidation review.
4. Feedback endpoints/UI and admin quality dashboard.
5. Durable analysis/OCR/export jobs plus SSE token, progress and agent-trace streaming.
6. Tier 3 case intelligence, expanded police/advocate strategy, courtroom simulation,
   and academic ablation evaluation only after Tier 2 gates pass.

Do not bulk-promote PDFs from `data/source_materials/` into Gold. Ten candidate
files still require provenance/quality review; seven are exact Gold duplicates.

## Safe shutdown

```bash
docker compose --env-file .env -f docker/docker-compose.yml stop
```

Do not use `down -v`; that deletes PostgreSQL, Qdrant, MinIO, and Ollama data.
