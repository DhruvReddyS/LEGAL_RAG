# Tauri desktop acceptance

Last verified: **2026-08-27 IST**

## Release result

The Next.js 14 static export is packaged as **Aegis Legal Intelligence 0.2.0**
with Tauri v2. The release build completed on Apple Silicon and produced:

- `Aegis Legal Intelligence.app` — 9.6 MB, arm64, macOS 11+
- `Aegis Legal Intelligence_0.2.0_aarch64.dmg` — 2.8 MB
- bundle identifier `in.ac.legalrag.desktop`
- explicit ad-hoc local signature that passes strict deep `codesign` verification
- DMG SHA-256 `6ff0707b05e3eff11051f5118852df097281930e885cd30402950dd59d88cb46`

The source build uses Tauri CLI 2.11.4, Tauri Rust 2.11.5, Rust 1.98.0 and
Cargo 1.98.0. The app has a branded icon, constrained minimum window size and a
content-security policy limited to bundled assets and the local API.

## One-command local start

Docker Desktop and host Ollama should be running. From the project root:

```bash
./scripts/start_desktop.sh
```

The launcher checks `.env` and Docker, starts PostgreSQL, Qdrant, MinIO and the
backend, waits for the warmed API health check, warns if Ollama is unavailable,
builds the desktop package if absent, and opens the native application.

The bundled UI is self-contained, but the legal corpus, database, vector store,
object store and self-hosted LLM remain local services. Fast Research remains
available without Ollama; Deep Review requires Ollama and the configured model.

## RBAC acceptance

Authorization is enforced by the FastAPI dependencies and resource ownership
checks, not merely by hiding frontend controls. The desktop UI reads `/auth/me`
after cookie authentication and loads the matching operating console:

| Role | Experience | Principal boundary |
| --- | --- | --- |
| Citizen | guided legal information and global-corpus research | cannot access professional cases or administration |
| Police | investigation research, police cases, evidence and FIR drafting | only owned police cases and police collection |
| Advocate | authority research, advocate cases and defence analysis | only owned advocate cases and advocate collection |
| Admin | account governance, corpus intake and audit activity | governance APIs; not presented as a case owner |

Four local demo accounts were verified through the cookie login endpoint. For
Citizen, Police and Advocate, `/admin/overview` returned `403`; for Admin it
returned `200`. All four `/auth/me` responses returned the expected role. Demo
passwords are intentionally not stored in tracked documentation.

The launched native process remained active and generated successful CORS
preflights from the Tauri origin, a public corpus-progress request, and the
expected unauthenticated session check. The desktop API resolver was explicitly
hardened so a Tauri custom origin always calls `http://localhost:8000` rather
than constructing an invalid custom-protocol API URL.

The latest regression gate passed **105 backend tests** with one
upstream Passlib/Python deprecation warning. The Next.js production build,
TypeScript validation, static export, Rust release compilation and `cargo fmt`
check also passed. PostgreSQL, Qdrant, MinIO and the backend were healthy, host
Ollama was reachable, and the native process remained running after launch.
The final package also contains the role-aware Document Analyzer, restored
analysis results, `A` shortcut and seven-field Evidence Inspector.

## Build and inspect

```bash
cd frontend
source "$HOME/.cargo/env"
npm install
npm run desktop:build
```

Artifacts:

```text
frontend/src-tauri/target/release/bundle/macos/Aegis Legal Intelligence.app
frontend/src-tauri/target/release/bundle/dmg/Aegis Legal Intelligence_0.2.0_aarch64.dmg
```

Local signature verification:

```bash
codesign --verify --deep --strict --verbose=2 \
  "frontend/src-tauri/target/release/bundle/macos/Aegis Legal Intelligence.app"
```

## Manual work before external distribution

The current package is accepted for local capstone demonstration. Public or
cross-device distribution still requires an Apple Developer ID Application
certificate and Apple notarization credentials, followed by a signed,
notarized build. An Intel or universal build must also be produced if the target
Mac is not Apple Silicon. Demo passwords must be changed or the demo accounts
deleted before any non-local deployment, and real evidence must never be placed
in these demo accounts.

## Dependency audit qualification

`npm audit` reports two high findings through Next.js 14 and its bundled
PostCSS. The automatic fix is a breaking upgrade to Next.js 16, which conflicts
with the locked Next.js 14 stack. This application uses a static export and does
not run the affected Next.js server, Server Actions, image optimizer, rewrites,
or WebSocket upgrade paths in production. The finding is therefore documented
as a constrained build-time/static-export risk; migration to a supported
patched Next.js major remains a pre-production backlog item.
