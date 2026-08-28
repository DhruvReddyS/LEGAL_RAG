# Aegis Legal Intelligence — local demo manual

> **Local capstone credentials only.** Do not reuse these passwords, expose the
> application to the internet, or upload real case evidence. Change or delete
> every demo account before any non-local deployment.

## 1. Start the desktop system

Start Docker Desktop and Ollama, then run:

```bash
cd "/Users/sripathidhruvreddy/Documents/MAJOR PROJECT"
./scripts/start_desktop.sh
```

The launcher starts PostgreSQL, Qdrant, MinIO and FastAPI, waits for the warmed
backend, checks Ollama, and opens the native Tauri application.

To stop the server components without deleting data:

```bash
docker compose --env-file .env -f docker/docker-compose.yml stop
```

Never use `docker compose down -v` unless all database, vector and object-store
data is intentionally being deleted.

## 2. How the desktop app reaches Ollama

```text
Tauri desktop UI
    │ HTTPS-style local fetch with secure cookie/RBAC
    ▼
FastAPI on http://localhost:8000
    │ retrieval → PostgreSQL + Qdrant + MinIO
    │ generation through http://host.docker.internal:11434/api/generate
    ▼
Ollama on this Mac → qwen3-14b-16k:latest
```

Tauri never sends prompts directly to Ollama. FastAPI first enforces the logged-in
role and case ownership, retrieves only authorised evidence, then sends a bounded
prompt to Ollama. The active settings are:

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3-14b-16k:latest
```

**Fast Research** uses retrieval only and can work when Ollama is unavailable.
**Deep Review** runs the verified multi-agent generation path and requires
Ollama. **Auto** selects between them from query complexity and case scope.

Quick checks:

```bash
curl --fail http://localhost:8000/health
ollama list
docker compose --env-file .env -f docker/docker-compose.yml ps
```

## 3. Demo credentials

| Role | Email | Password |
| --- | --- | --- |
| Citizen | `citizen.demo.aegis@example.com` | `CitizenDemo#2026!` |
| Police | `police.demo.aegis@example.com` | `PoliceDemo#2026!` |
| Advocate | `advocate.demo.aegis@example.com` | `AdvocateDemo#2026!` |
| Admin | `admin.demo.aegis@example.com` | `AdminDemo#2026!` |

There is no role selector. The server reads the account role after login and
loads its dedicated interface, agents, shortcuts and authorised data boundary.

## 4. Citizen walkthrough

Expected interface: Citizen command centre and plain-language legal research.

Try these in **Fast**, **Auto**, and **Deep** modes:

1. `My dog is missing in Bengaluru. How should I report it, what details should I preserve, and when would an FIR be appropriate?`
2. `Explain Article 14 reasonable classification in plain language and cite the supporting pages.`
3. `A police officer refused to record information about a cognizable offence. What is the lawful escalation process?`

Check that every legal proposition has a source card/page reference, weak
evidence is labelled, and the system abstains rather than inventing authority.
Citizen must not see professional cases, evidence upload, FIR drafting or Admin.

## 5. Police walkthrough

Expected interface: investigation command centre, police-only cases, evidence
intake, procedure search and FIR drafting.

1. Create a matter named `Demo — Missing dog complaint`.
2. Upload a harmless TXT/PDF containing this fictional account:

   `Complainant Asha Rao, phone 9000000000, reports that her brown female Indie dog Tara, blue collar number BLR-104, was last seen near Cubbon Park Gate 2 at 18:30 on 25 August 2026. CCTV may cover the gate. No theft was witnessed and no suspect is known.`

3. Classify it as `FIR / complaint` or `Witness statement` and index it.
4. Search the selected matter for `last-seen identifiers, CCTV and missing facts`.
5. Paste the scenario into the FIR drafting assistant.
6. Open **Document Analyzer** (`A`), select the indexed file, enter an optional
   focus and run the structured analysis. Click any evidence or authority chip
   to open the Evidence Inspector.

Check that unknown facts remain visibly missing, theft is not invented, sources
are reviewable, and only the selected police matter is retrieved.

A ready-made matter named `Demo — Document Analyzer acceptance` is already
available in the Police demo account. Its fictional statement produced three
grounded clauses and three risks in the live acceptance run.

## 6. Advocate walkthrough

Expected interface: advocate matter command centre, private client evidence,
two-sided authority research and defence analysis.

1. Create a matter named `Demo — Electronic evidence challenge`.
2. Upload a fictional TXT/PDF stating:

   `The prosecution relies on exported chat screenshots. The original phone was not seized, the export method is undocumented, timestamps differ from the server log by two hours, and the witness who produced the screenshots cannot identify who controlled the account. The prosecution says the accused admitted ownership of the number.`

3. Classify it as `Opposing filing` or `Evidence exhibit` and index it.
4. Search for `electronic evidence authenticity, chain of custody and adverse prosecution arguments`.
5. Run the defence analysis and inspect both supporting and opposing points.
6. Run the same indexed file through **Document Analyzer** and compare its
   clause/risk view with the two-sided strategy output.

Check that the system rejects concealment, fabrication or witness coaching,
separates scenario facts from legal authority, and exposes verification status.

## 7. Administrator walkthrough

Expected interface: account governance, governed global-corpus intake and audit
trail—not a professional case workspace.

1. Review Police and Advocate accounts and their active/suspended state.
2. Suspend a disposable professional demo account and confirm its current session
   loses access; reactivate it afterwards.
3. Stage only a public, official legal PDF with its real source URL, jurisdiction
   and issuing authority.
4. Run validation, review page/extraction/OCR metrics, then publish only if the
   source passes governance checks.
5. Review the append-only audit activity for account and corpus actions.

Do not promote random web PDFs or the inactive `data/source_materials` directory
into the verified corpus without provenance and deduplication review.

## 8. Useful shortcuts

- `⌘K` — command palette
- `D` — role command centre
- `R` — legal research
- `C` — professional case/Admin workspace when authorised
- `A` — Document Analyzer for Police and Advocate
- `N` — new research
- `Esc` — close the command palette

## 9. Expected performance and limitations

- Warm Fast Research acceptance: p95 about **449 ms** at concurrency 1.
- Target: Fast responses under **5 seconds** on this development machine.
- Deep Review is model-bound and can take much longer with the local 14B model.
- The current macOS package is Apple Silicon and locally signed. External
  distribution needs Apple Developer ID signing and notarization.
- The legal output is decision support for professional review, not legal advice
  or a prediction of a court outcome.

Detailed validation is recorded in `TAURI_DESKTOP_ACCEPTANCE.md`,
`ROLE_BASED_ACCEPTANCE.md`, `RAG_STRESS_TEST_REPORT.md`, and
`INGESTION_ASSESSMENT.md`.
