# GitHub release and local setup

Updated: **2026-08-28 IST**

## Release architecture

Stage 1 distributes Aegis Legal Intelligence as a signed Tauri desktop client
through GitHub Releases. The client calls FastAPI at `http://localhost:8000`.
The following services continue to run locally through Docker Compose:

- FastAPI, PostgreSQL, Qdrant and MinIO;
- the BGE embedding and reranking runtime inside the backend container;
- the legal corpus mounted from `data/legal_kb`;
- Ollama on the host at port `11434` for Deep Review and other generated output.

The backend reaches host Ollama through
`OLLAMA_BASE_URL=http://host.docker.internal:11434`. The Tauri client does not
call Ollama directly. Fast Research remains usable when Ollama is unavailable;
Deep Review requires the configured model.

An installer by itself is therefore not a standalone installation in Stage 1.
Each release must also provide a version-matched runtime bundle containing the
Compose file, `.env.example`, launcher scripts and corpus-install instructions,
or a source checkout at the same tag. Publishing the backend image to GHCR is
recommended so end users do not need to compile it locally.

Stage 2 may bundle a managed FastAPI sidecar and first-run service supervisor.
It must not be advertised as implemented yet; PostgreSQL, Qdrant, object
storage, corpus delivery, upgrades, recovery and Ollama discovery still require
a deliberate cross-platform design.

## Supported systems

| Platform | Status | Package |
| --- | --- | --- |
| macOS 11+, Apple Silicon | Verified locally | `.dmg` / `.app` |
| macOS 11+, Intel | Planned Stage 1 CI build; not yet verified | `.dmg` / `.app` |
| Windows 10/11 x64 | Planned Stage 1 CI build; not yet verified | NSIS `.exe` (preferred) |
| Windows ARM64, Linux | Future | Not currently supported |

Build each target on its native GitHub runner. Do not rely on cross-compiling
signed macOS or Windows installers. The current Tauri configuration targets
only `app` and `dmg`, so Windows targets must be added and accepted before a
Windows release is claimed.

## Stage 1 prerequisites

Install these before first launch:

1. Docker Desktop with Compose v2. On Windows use the WSL2 backend.
2. Ollama for the host operating system.
3. The desktop package and version-matched runtime bundle/source tag.
4. The approved `data/legal_kb` corpus. Do not publish private case data or
   unlicensed corpus material in a public GitHub release.
5. Enough disk and memory for Docker, the corpus, BGE models and the selected
   Ollama model.

Pull the exact model named by `.env`, currently:

```bash
ollama pull qwen3-14b-16k:latest
ollama list
```

Model names are exact identifiers. If a different locally installed model is
used, set `OLLAMA_MODEL` to that exact value before starting the backend.

## First run

From the version-matched project/runtime directory:

```bash
cp .env.example .env
```

Replace every `CHANGE_ME`, set a strong PostgreSQL password, and keep `.env`
outside version control. Use independent random JWT access and refresh secrets.
Then start Ollama and Docker Desktop.

On the currently verified macOS package:

```bash
./scripts/start_desktop.sh
```

The launcher starts PostgreSQL, Qdrant, MinIO and FastAPI, waits for
`http://localhost:8000/health`, checks Ollama, and opens the application. The
backend entrypoint automatically applies Alembic migrations and creates the
Qdrant collections and MinIO buckets. Windows needs an equivalent signed
PowerShell launcher before Stage 1 Windows acceptance.

Verify the runtime:

```bash
docker compose --env-file .env -f docker/docker-compose.yml ps
curl http://localhost:8000/health
curl http://localhost:11434/api/tags
```

Create real police, advocate and administrator accounts with the existing
account scripts. Shared demo credentials are for local demonstration only and
must not be shipped as production defaults.

## GitHub Releases and automatic updates

Use semantic versions and annotated tags such as `v0.3.0`. The version must
match in all three files before tagging:

- `frontend/package.json`;
- `frontend/src-tauri/Cargo.toml`;
- `frontend/src-tauri/tauri.conf.json`.

A release workflow should run the complete backend tests, Next.js static build,
Rust formatting/checks, and native package smoke tests on every supported build
runner. It should publish signed installers, checksums, release notes and the
version-matched runtime bundle. Only release from a protected tag whose commit
passed all gates.

Automatic updates are **not implemented in the current repository**. Completing
them requires the Tauri v2 updater plugin in Rust and JavaScript, updater
capabilities, `bundle.createUpdaterArtifacts`, a public verification key and a
GitHub Release endpoint. The workflow must publish Tauri updater signatures and
an HTTPS `latest.json` manifest containing every supported target. The client
must offer the update, verify its signature, install it, restart safely and show
a recoverable error if the runtime bundle is incompatible.

Never auto-update the desktop independently across a breaking API, database,
Qdrant schema or corpus format change. Include a compatibility version in both
client and `/health`, and block incompatible upgrades with a clear instruction.

Recommended release sequence:

1. Update versions and compatibility notes.
2. Run all acceptance gates and build native artifacts.
3. Sign, notarize where required, and verify installers on clean machines.
4. Tag `vX.Y.Z` and publish a draft GitHub Release.
5. Upload installers, checksums, updater signatures/manifest and runtime bundle.
6. Promote the draft only after a clean-machine install and update-from-previous
   version test passes.

## Signing and CI secrets

Store secrets only in protected GitHub environments. Do not place certificates,
private keys or passwords in the repository or release assets.

macOS requires an Apple Developer ID Application certificate and notarization
credentials (Apple API issuer/key or Apple ID, Team ID and app-specific
password). Windows requires a trusted code-signing certificate or managed
signing service. Tauri updater artifacts require
`TAURI_SIGNING_PRIVATE_KEY` and its password; only the corresponding public key
belongs in application configuration. The release job also needs a scoped
GitHub token for release uploads and, if used, GHCR publication.

The current macOS build uses an ad-hoc local signature. It is valid for the
capstone machine but is not suitable for public distribution or auto-update.

## Local data and backups

Persistent state is local and is not removed by an application update:

| Data | Location |
| --- | --- |
| PostgreSQL | Compose volume `postgres_data` |
| Qdrant vectors | Compose volume `qdrant_data` |
| MinIO objects and versions | Compose volume `minio_data` |
| Optional container Ollama | Compose volume `ollama_data` |
| Host Ollama models | `~/.ollama` on macOS; `%USERPROFILE%\.ollama` on Windows |
| Approved corpus/cache | `data/legal_kb` bind-mounted at `/data/legal_kb` |
| Secrets | project-root `.env` |

The Compose project name is `multi-agent-legal-rag`; Docker may display the
named volumes with that project prefix.

Before an update or corpus migration, stop writes and back up PostgreSQL with
`pg_dump`, create snapshots for all three Qdrant collections, export/version the
MinIO buckets, and copy `data/legal_kb` plus `.env` to encrypted storage. Keep
the backup separately from Docker Desktop. Test a full restore on a clean
machine before using real evidence. `docker compose down -v` deletes the named
volumes and must never be used as a routine shutdown command.

Safe shutdown:

```bash
docker compose --env-file .env -f docker/docker-compose.yml stop
```

## Manual work still required

- Create the GitHub repository, protected release environment and native build
  matrix; no `.github` workflow exists yet.
- Decide whether the runtime bundle uses a versioned GHCR backend image or a
  local source build, and define corpus licensing/delivery.
- Implement and test the Tauri updater; it is not currently configured.
- Obtain Apple and Windows signing identities and add protected CI secrets.
- Add Windows installer targets and a PowerShell first-run launcher.
- Build and test Intel macOS and Windows x64 packages on clean machines.
- Define client/API/database/Qdrant/corpus compatibility and rollback policy.
- Automate encrypted backups, Qdrant snapshots and restore drills.
- Remove shared demo accounts and rotate all local secrets before non-demo use.

## Release acceptance criteria

A platform/architecture is supported only when all of the following pass:

- clean install, first run, login and all four RBAC experiences;
- backend migrations, three Qdrant collections, MinIO buckets and corpus health;
- host Ollama discovery plus a grounded Deep Review using the configured model;
- Fast Research remains functional and clearly labels Ollama-independent output;
- update from the previous release with signature verification and preserved data;
- tampered installer/update rejection, invalid-signature rejection and rollback;
- cross-owner/cross-role private evidence isolation;
- PostgreSQL, Qdrant, MinIO and corpus backup/restore rehearsal;
- uninstall behavior explicitly preserves or offers removal of local legal data;
- signed artifact, checksum and clean-machine malware/security scan verification.
