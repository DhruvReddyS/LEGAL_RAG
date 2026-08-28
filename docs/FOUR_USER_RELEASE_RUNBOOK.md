# Optional offline four-user architecture

Updated: **2026-08-28 IST**

## Alternative A: one complete offline stack per device

This is retained for future air-gapped/disaster-recovery work. The selected
normal deployment is the lightweight shared-service design in
[SCALABLE_DEPLOYMENT_RUNBOOK.md](SCALABLE_DEPLOYMENT_RUNBOOK.md), because it
avoids duplicating the corpus and models on every laptop.

The target is four independent, private installations. Each computer owns its
Tauri UI, FastAPI service, databases, vector indexes, object store, embeddings,
legal-corpus snapshot and Ollama model. Normal use requires neither a central
server nor an Internet connection:

```text
Citizen device:  Tauri -> localhost FastAPI -> PostgreSQL/Qdrant/MinIO -> Ollama
Police device:   Tauri -> localhost FastAPI -> PostgreSQL/Qdrant/MinIO -> Ollama
Advocate device: Tauri -> localhost FastAPI -> PostgreSQL/Qdrant/MinIO -> Ollama
Admin device:    Tauri -> localhost FastAPI -> PostgreSQL/Qdrant/MinIO -> Ollama
```

This is the strongest privacy and outage-isolation model for the pilot. A
device can be powered off without affecting the others, and case material does
not leave that device. The trade-off is four copies of the model, corpus and
indexes, four backup obligations, and no automatic cross-device synchronization.
An admin on one device cannot suspend accounts or publish corpus changes on the
other three devices until a secure provisioning/synchronization mechanism is
implemented.

### Honest current status

The v0.3.0 Tauri package contains the static UI and native shell only.
It does **not** currently bundle FastAPI, PostgreSQL, Qdrant, MinIO, the corpus,
BGE models or Ollama. The accepted developer runtime uses Docker Compose plus a
native Ollama on one Apple Silicon machine. Therefore a clean-machine,
single-installer offline release is a **target architecture**, not a completed
release claim.

The current localhost frontend default is correct for offline deployment:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Do not compile a remote API URL into an offline build. Keep PostgreSQL, Qdrant,
MinIO, FastAPI and Ollama bound to loopback; the Tauri application calls
FastAPI, and FastAPI alone calls storage, retrieval and Ollama.

### Offline release blockers

Before calling this a smooth four-device installer, complete and verify:

1. Package the FastAPI runtime as an OS-specific sidecar or managed local
   service, including migrations, health checks and clean shutdown.
2. Bundle or safely bootstrap pinned PostgreSQL, Qdrant and MinIO services.
   Requiring Docker Desktop is acceptable only for the technical pilot, not
   for the promised consumer-style installer.
3. Create a signed, versioned corpus pack containing the canonical legal data,
   Qdrant-compatible indexes or a reproducible local import, a manifest and
   checksums. Corpus updates need validation and rollback; copying a mutable
   working directory is not an update mechanism.
4. Bootstrap Ollama and the approved model locally, or detect an existing
   compatible installation. Model downloads are large and require an explicit
   progress, disk-space and checksum experience.
5. Define local first-run account provisioning. Each independent installation
   needs a local administrator or a signed role-specific provisioning package;
   the repository does not yet provide fleet-wide identity synchronization.
6. Exercise macOS arm64, macOS x64 and Windows x64 on clean machines. The
   current `scripts/start_desktop.sh` is macOS-specific and is not a Windows
   installer/bootstrap path.
7. Apply Developer ID signing/notarization on macOS and trusted Windows code
   signing. Tauri updater signatures do not replace OS signing.
8. Decide how signed application and corpus updates reach offline devices.
   Manual verified media is valid; an updater cannot silently depend on a
   private GitHub token embedded in the application.

### Practical staged rollout

**Stage 1 — supervised technical offline pilot.** On each computer install
Docker Desktop, Ollama, the pinned model, the repository/runtime dependencies
and the same validated corpus snapshot. Create that device's own `.env`, start
its local Compose stack, build/install the matching Tauri application, and run
the role checklist below. This is reproducible for technical testers but is not
a one-click product installation.

**Stage 2 — productized offline release.** Replace repository and Docker
prerequisites with signed OS installers that manage the backend and data
services, perform first-run capacity checks, import signed corpus/model packs,
provision the local role, expose health/recovery controls, and support atomic
update/rollback. Acceptance must occur on a clean Mac and clean Windows PC.

### Per-device sizing and Ollama placement

- The currently accepted host is Apple Silicon with 24 GB unified memory and
  `qwen3-14b-16k:latest`. Use this as the known baseline, not as proof that
  every 24 GB or Windows device will perform identically.
- Plan for at least 100 GB free SSD space per device for services, corpus,
  indexes, model and one local backup; retain at least 20% free space.
- A 16 GB device may run Fast Research or a smaller model only after a
  controlled quality/latency benchmark. Do not promise the accepted 14B Deep
  profile on untested hardware.
- Native Ollama on every device is the preferred offline inference placement.
  Fast Research remains available when Ollama is stopped; Deep Review does not.
- The current Deep 14B workflow exceeded 180 seconds in stress acceptance, so
  it is not a five-second experience even when fully local.

### Offline installation and verification (technical pilot)

Repeat these steps independently on every device. Use only synthetic case data
until that device has passed the isolation and backup checks.

1. Install Docker Desktop and native Ollama from their official sources.
2. Transfer a version-pinned repository/corpus bundle over verified media.
   Compare its SHA-256 manifest before extracting it.
3. Copy `.env.example` to `.env`; generate new device-local database, JWT and
   S3 secrets. Never reuse secrets across the four computers.
4. Install/pull the approved Ollama model and confirm `ollama list` shows the
   exact configured name.
5. Start and verify the local service plane:

   ```bash
   docker compose --env-file .env -f docker/docker-compose.yml up -d --build
   docker compose --env-file .env -f docker/docker-compose.yml ps
   curl --fail http://127.0.0.1:8000/health
   ```

6. Run strict corpus validation and the test commands in
   [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md). Expected accepted corpus counts are
   381 canonical documents, 17,426 pages and 25,517 Gold Qdrant points.
7. Install the matching signed Tauri artifact. On macOS verify `codesign`,
   Gatekeeper and notarization; on Windows verify SHA-256 and Authenticode.
8. Provision only the intended local role, then execute the four-role/isolation
   checklist below as applicable. A role claim in the UI is not proof; denied
   API access must also be verified.

Windows users can run Compose commands in PowerShell, but the current repository
does not include a Windows equivalent of `scripts/start_desktop.sh`. That gap is
why Stage 1 requires supervised technical setup.

### Per-device data, backup and update policy

Every machine is its own system of record. Back up PostgreSQL, MinIO, all three
Qdrant collections and `data/legal_kb` together on that machine. Encrypt backup
media and test restore in an isolated environment. The detailed commands in
section 9 are developer operations and must be run separately per device; do
not assume the admin computer backs up other offline computers.

There is deliberately no live case-data sync. If a case must move between
devices, use a future encrypted, signed export/import workflow with audit
records; ad-hoc database copies are not an accepted transfer path. Application,
model and corpus updates must be versioned independently, checksum-verified and
reversible. Until this exists, update each machine under supervision and retain
its previous installer plus coordinated backup.

### Offline four-device acceptance

On every device, disconnect Wi-Fi/Ethernet after local startup and confirm login,
Fast Research, citation inspection, logout and restart still work. Confirm the
API and service ports are reachable only from loopback. Run ten warmed Fast
queries and record median/p95; the accepted target is p95 below five seconds.

Use synthetic data for the role check:

- Citizen: ask the missing-dog/FIR-information scenario, inspect global sources,
  and verify professional case and admin APIs are denied.
- Police: create/upload/index/analyze a synthetic owned case, draft an FIR with
  missing facts explicit, and verify another owner's case ID and admin APIs are
  denied.
- Advocate: run two-sided defence analysis on an owned synthetic case, inspect
  evidence/legal links, and verify police/admin resources are denied.
- Admin: exercise governed account/corpus/audit controls locally and verify that
  the action has no implied effect on the other offline installations.

Record app/backend/corpus/model versions, OS/architecture, role, Fast p95, Deep
completion time and pass/fail. Any network dependency, cross-role access,
invalid citation, missing audit event or silent cloud fallback is a blocker.

## Selected deployment: one shared backend over Tailscale

The remaining network-specific sections describe the selected scalable pilot:

```text
Citizen Mac/PC ─┐
Police Mac/PC  ─┼─ Tailscale private HTTPS ─ aegis-host:443 ─ FastAPI
Advocate Mac/PC─┤                                      ├─ PostgreSQL
Admin Mac/PC   ─┘                                      ├─ Qdrant
                                                       ├─ MinIO
                                                       └─ host Ollama
```

Tailscale is the private network boundary; FastAPI JWT/RBAC remains the
application authorization boundary. The two controls are complementary. Never
publish this pilot with Tailscale Funnel, router port-forwarding, or a public
Ollama, PostgreSQL, Qdrant or MinIO port.

This is a single-host pilot, not high availability. If the host sleeps, loses
power or Internet, all four users lose service.

## Alternative-B release blockers before friends install

Do not distribute the current localhost package as a multi-device build. All of
these gates must be satisfied first:

1. In the desktop readiness screen, enter
   `https://aegis-host.<tailnet>.ts.net`, test `/health`, then save and reconnect.
   The origin is validated and stored at runtime, so changing hosts does not
   require rebuilding the desktop app.
2. Produce and test macOS arm64, macOS x64 and Windows x64 packages. Give each
   person only the package matching their operating system and architecture.
3. For a smooth external macOS install, use a Developer ID Application
   certificate and Apple notarization. The current ad-hoc signature is for
   local testing, not friend distribution.
4. For a smooth Windows install, use a trusted Authenticode/Artifact Signing
   identity. Tauri updater signatures do **not** replace operating-system code
   signing.
5. Decide updater hosting. An updater URL under a private GitHub repository is
   not usable by an unauthenticated desktop updater; never embed a GitHub token
   in the application. For this pilot either:
   - use a separate public, binary-only signed release repository while the
     backend and source remain private; or
   - distribute every accepted update manually to the four known users and
     treat updater-check failure as expected until a tailnet-private update
     endpoint is implemented.
6. Keep Fast Research as the default. The local 14B Deep workflow has exceeded
   180 seconds under acceptance testing and is not yet a five-second path.

## 1. Host requirements

### Recommended host

- Dedicated or reliably available Apple Silicon Mac with **24 GB unified memory
  minimum**, 32 GB preferred for more headroom.
- macOS 12 or later for the current Tailscale client; a supported, fully patched
  macOS release is preferred.
- At least 100 GB free SSD space after the corpus, models and first backup. Keep
  20% of the disk free; Qdrant restore operations can temporarily need roughly
  twice a collection's disk usage.
- Stable broadband, wired Ethernet where practical, and power protection.
- Docker Desktop, Tailscale Standalone, native Ollama, Git and the repository.
- Automatic OS security updates, disk encryption and a non-shared administrator
  account.

Use the native macOS Ollama installation on this host. It can use Apple GPU
acceleration, while the backend container reaches it through
`host.docker.internal:11434`. Do not install the optional Docker Ollama profile
at the same time.

In macOS settings, enable restart after power failure where available and
prevent automatic system sleep while the display is off. Docker Desktop,
Tailscale and Ollama must start after reboot. Schedule a short weekly maintenance
window for OS/container updates and a verified restart.

### Host-only port binding

Copy `.env.example` to `.env`, generate strong independent secrets, and use this
pilot overlay. Values such as `<tailnet>` are placeholders, not literal text.

```dotenv
APP_ENV=production
CORS_ORIGINS=http://tauri.localhost,tauri://localhost
COOKIE_SECURE=true
COOKIE_SAMESITE=none

BACKEND_BIND_ADDRESS=127.0.0.1
BACKEND_PORT=8000
POSTGRES_PORT=5432
QDRANT_HTTP_PORT=6333
QDRANT_GRPC_PORT=6334

OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3-14b-16k:latest
```

Compose combines the backend bind address and numeric port, while the database,
vector store, and MinIO mappings are fixed to loopback. Confirm with
`docker compose config` before
starting. Do not place `.env`, signing keys, real case data or passwords in Git.

Start Ollama and confirm the selected model exists:

```bash
ollama list
curl --fail http://127.0.0.1:11434/api/tags
```

Then start the service plane:

```bash
cd "/Users/sripathidhruvreddy/Documents/MAJOR PROJECT"
docker compose --env-file .env -f docker/docker-compose.yml up -d
docker compose --env-file .env -f docker/docker-compose.yml ps
curl --fail http://127.0.0.1:8000/health
```

All four long-running containers must be healthy. `minio-init` should exit
successfully after creating/versioning buckets.

## 2. Configure the private Tailscale boundary

Use the [Tailscale Standalone macOS client](https://tailscale.com/docs/concepts/macos-variants)
on the host. In the Tailscale admin console:

1. Keep MagicDNS enabled and enable HTTPS certificates.
2. Rename the host to `aegis-host` and record its complete
   `aegis-host.<tailnet>.ts.net` name.
3. Invite the other three people as separate external users. Never share one
   Tailscale identity; one-time invites expire after 30 days according to the
   [official invite guide](https://tailscale.com/docs/features/sharing/how-to/invite-any-user).
4. Put the four named identities in `group:aegis-users` and the dedicated host
   under `tag:aegis-server`.
5. Remove any broad default rule that already gives members access to every
   device/port, then grant only TCP 443 to this server. Tailscale grants are
   additive, so a broad rule would defeat the narrow one.

Policy sketch—replace all example emails with the four actual identities and
merge it carefully with the existing tailnet policy:

```json
{
  "groups": {
    "group:aegis-users": [
      "owner@example.com",
      "citizen@example.com",
      "police@example.com",
      "advocate@example.com"
    ]
  },
  "tagOwners": {
    "tag:aegis-server": ["autogroup:admin"]
  },
  "grants": [
    {
      "src": ["group:aegis-users"],
      "dst": ["tag:aegis-server"],
      "ip": ["tcp:443"]
    }
  ]
}
```

Tailscale's current [grants documentation](https://tailscale.com/docs/features/access-control/grants)
describes the deny-by-default and additive behavior. Use the policy editor's
tests to assert that each named user can reach `tag:aegis-server:443` and cannot
reach ports 8000, 9000, 9001, 5432, 6333, 6334 or 11434.

Expose the loopback API through private HTTPS only:

```bash
tailscale serve --bg --https=443 http://127.0.0.1:8000
tailscale serve status
```

`tailscale serve` provisions TLS for the private MagicDNS name and keeps the
service within the tailnet. This current syntax is documented in the
[Serve CLI reference](https://tailscale.com/docs/reference/tailscale-cli/serve).
Do not run `tailscale funnel`.

Verify from the host:

```bash
curl --fail https://aegis-host.<tailnet>.ts.net/health
```

The expected body is `{"status":"healthy"}` with a valid TLS certificate.

## 3. Build and accept the environment-specific release

The same fixed private API URL must be present in all three release jobs:

```text
NEXT_PUBLIC_API_URL=https://aegis-host.<tailnet>.ts.net
```

For a local same-platform check:

```bash
cd frontend
NEXT_PUBLIC_API_URL=https://aegis-host.<tailnet>.ts.net npm run desktop:build
```

Use the GitHub matrix for the actual arm64/x64/Windows release. Keep the release
as a draft until all tests pass. Verify that:

- version/tag consistency, backend tests, frontend lint/static build and all
  native jobs pass;
- `latest.json` and a `.sig` updater signature for every target exist;
- `latest.json` contains `darwin-aarch64`, `darwin-x86_64` and
  `windows-x86_64` with HTTPS URLs and non-empty signatures;
- the packaged JavaScript contains the private HTTPS API URL and does not point
  to `localhost:8000`;
- macOS artifacts pass `codesign`, Gatekeeper assessment and notarization; and
- Windows reports the expected publisher and a valid Authenticode signature.

Create a SHA-256 manifest and send its hash to users over a second trusted
channel. Never modify an installer after signing.

## 4. Create four application accounts

Use four unique accounts—one `citizen`, one `police`, one `advocate`, and one
`admin`. Network membership does not determine the application role. Create
professional/admin accounts through the existing governed account process,
use randomly generated unique passwords, and send each password separately
from the installer and Tailscale invite.

Do not reuse the published local demo credentials. Do not put passwords in this
runbook, release notes, chat screenshots or the GitHub repository. The admin
must suspend a user's application account and remove their Tailscale identity
when that person leaves the pilot.

## 5. Friend installation—common first steps

For each person, onboard one device at a time:

1. Accept the individual Tailscale invite using that person's own identity.
2. Install the stable Tailscale client and approve its VPN/system extension.
3. Log in and wait for the admin to approve/tag the device if policy requires.
4. Open `https://aegis-host.<tailnet>.ts.net/health` in a browser. Stop if TLS
   is invalid or the response is not `{"status":"healthy"}`.
5. Download the accepted Aegis installer from the approved release channel.
6. Compare its SHA-256 with the out-of-band manifest before opening it.
7. Install Aegis, log in with the assigned account, and confirm the displayed
   role before entering any case information.

### Windows 10/11 x64

Install Tailscale from its official Windows package; the current client requires
Windows 10 or later. The [official MSI instructions](https://tailscale.com/kb/1189/install-windows-msi/)
cover installation and login.

Verify the Aegis installer in PowerShell:

```powershell
Get-FileHash .\Aegis-Legal-Intelligence-Setup.exe -Algorithm SHA256
Get-AuthenticodeSignature .\Aegis-Legal-Intelligence-Setup.exe | Format-List
```

The hash must match the release manifest and `Status` should be `Valid` for a
production-signed build. A new valid publisher can still receive a SmartScreen
reputation warning; Microsoft's [current SmartScreen guidance](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation)
explains that signing does not instantly create reputation. Never ask users to
disable Defender or SmartScreen. If the package is unsigned, limit installation
to a supervised capstone pilot after independent hash verification; managed
Windows policy may correctly prevent installation.

Client network check:

```powershell
tailscale ping aegis-host
Invoke-RestMethod https://aegis-host.<tailnet>.ts.net/health
```

### macOS arm64 or x64

Use Tailscale's recommended Standalone app; the current release requires macOS
12 or later. Do not install the Standalone and App Store variants together.

Verify the DMG before opening it:

```bash
shasum -a 256 "Aegis Legal Intelligence.dmg"
```

After copying Aegis into `/Applications`, verify a production package:

```bash
codesign --verify --deep --strict --verbose=2 \
  "/Applications/Aegis Legal Intelligence.app"
spctl --assess --type execute --verbose=4 \
  "/Applications/Aegis Legal Intelligence.app"
xcrun stapler validate "/Applications/Aegis Legal Intelligence.app"
```

Gatekeeper expects identified-developer signing and notarization. Apple's
[safe app-opening guidance](https://support.apple.com/en-gb/102445) warns that
unsigned/unnotarized software carries additional risk. Do not disable
Gatekeeper or distribute instructions that remove quarantine attributes. A
supervised pilot user may use System Settings → Privacy & Security → Open
Anyway only after independently verifying the hash and source.

Client network check:

```bash
tailscale ping aegis-host
curl --fail https://aegis-host.<tailnet>.ts.net/health
```

## 6. Four-role acceptance checklist

Run this after every server or desktop release. Use synthetic data only.

### Every device

- Tailscale is connected, private HTTPS health succeeds and direct attempts to
  reach host ports 8000/9000/9001/5432/6333/6334/11434 fail.
- Login survives one application restart and logout invalidates the session.
- A Fast Research query returns a grounded answer or explicit abstention, with
  source inspector fields visible. Run ten warmed Fast queries and record
  median/p95; the accepted target is p95 below five seconds.
- Disconnecting Tailscale produces a clear connectivity failure and does not
  fall back to an unrelated/public backend.

### Citizen

- Ask a synthetic missing-dog/FIR-information question.
- Confirm global-corpus sources are inspectable.
- Confirm no case workspace, professional evidence or admin APIs are available.

### Police

- Create an owned police case, upload a synthetic PDF, index it, analyze it and
  draft an FIR with unknown facts left visibly incomplete.
- Confirm another user's case ID cannot be read, searched, analyzed or changed.
- Confirm `/admin/overview` is denied.

### Advocate

- Create an owned advocate case and run a two-sided defence analysis using only
  synthetic allegations.
- Confirm strategy points link to case evidence/legal authority and unsafe or
  unsupported tactics are rejected.
- Confirm police and admin resources are denied.

### Admin

- Confirm the governance overview loads, create/suspend a temporary test
  professional account, inspect audit events and remove the test account from
  active use.
- Stage a disposable corpus file but do not publish it into Gold unless all
  provenance and quality gates pass.

Record release version, OS/architecture, device, user role, test timestamp,
Fast latency, Deep completion time, result and screenshot/log reference. Any
cross-role leak, invalid citation, broken TLS, missing audit event or silent
fallback is a release blocker.

## 7. Ollama placement and capacity trade-off

| Placement | Use now? | Trade-off |
| --- | --- | --- |
| Native Ollama on the backend Mac | **Recommended** | One governed model/corpus path and Apple acceleration; host failure affects everyone and Deep requests contend for one model. |
| Ollama inside Docker Desktop on the Mac | No | Easier lifecycle, but typically poorer access to Apple acceleration and duplicates the native service risk. |
| Ollama on each friend device | No | The central backend cannot use each client's `localhost`; models/configs diverge and offline clients remove capacity. Requires a different routing/security architecture. |
| Dedicated inference workstation/server | Later | Best concurrency and uptime; costs more and must be reachable only from the backend over a restricted private route. |

Ollama has no application-level RBAC boundary. Only FastAPI may call it. For
four users, allow one Deep request at a time, use Fast mode for interactive
work, and avoid ingestion/embedding during a demo. Monitor:

```bash
ollama ps
docker stats --no-stream
df -h
```

If Ollama is unavailable, Fast evidence research should remain usable; Deep
Review should be declared temporarily unavailable rather than silently using a
cloud model.

## 8. Uptime and operating routine

### Daily

- Check `tailscale serve status`, Docker health and `ollama list`.
- Confirm free disk remains above 20% and review failed login/audit events.
- Run one Fast health query before the user window opens.
- Tell users immediately about planned downtime or degraded Deep service.

### Weekly maintenance

1. Stop accepting new work and wait for active analysis/indexing to finish.
2. Take and verify the backup below.
3. Apply stable OS, Tailscale, Docker image and Ollama updates one layer at a
   time—never all at once immediately before a demo.
4. Restart the host and verify Tailscale, Serve, Ollama and every container.
5. Run the four-role smoke suite before reopening access.

For a pilot, use a declared operating window rather than pretending to provide
24×7 service. Record outages and recovery time. A second host/failover is
required before promising high availability.

## 9. Backups and restore drills

Target **RPO 24 hours** and **RTO 2 hours** for the pilot. Keep seven daily,
four weekly and three monthly encrypted copies, with at least one copy off the
host. Back up all four state classes together:

- PostgreSQL: users, cases, sessions, generated records and audit history.
- MinIO: uploaded evidence, corpus objects and generated documents.
- Qdrant: all three collections and their indexes/payloads.
- `data/legal_kb`: canonical corpus manifests/chunks plus configuration needed
  to reproduce embeddings.

The updater private key and `.env` need separate encrypted escrow; do not store
them unencrypted beside data backups.

Example short-maintenance backup from the project root. Choose an explicit
encrypted external destination before running it:

```bash
AEGIS_BACKUP_DIR="/Volumes/EncryptedBackup/aegis/2026-08-28"
AEGIS_COMPOSE="docker/docker-compose.yml"

mkdir -p "$AEGIS_BACKUP_DIR/postgres" \
  "$AEGIS_BACKUP_DIR/qdrant" \
  "$AEGIS_BACKUP_DIR/minio" \
  "$AEGIS_BACKUP_DIR/legal_kb"

docker compose --env-file .env -f "$AEGIS_COMPOSE" stop backend

docker compose --env-file .env -f "$AEGIS_COMPOSE" exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$AEGIS_BACKUP_DIR/postgres/legal_rag.dump"

for collection in global_legal_corpus police_case_data advocate_case_data; do
  snapshot_name="$(curl --fail --silent --show-error -X POST \
    "http://127.0.0.1:6333/collections/${collection}/snapshots" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["name"])')"
  curl --fail --silent --show-error \
    "http://127.0.0.1:6333/collections/${collection}/snapshots/${snapshot_name}" \
    --output "$AEGIS_BACKUP_DIR/qdrant/${snapshot_name}"
done

docker compose --env-file .env -f "$AEGIS_COMPOSE" stop minio
docker compose --env-file .env -f "$AEGIS_COMPOSE" cp \
  minio:/data/. "$AEGIS_BACKUP_DIR/minio"
rsync -a data/legal_kb/ "$AEGIS_BACKUP_DIR/legal_kb/"

docker compose --env-file .env -f "$AEGIS_COMPOSE" up -d minio minio-init backend
shasum -a 256 "$AEGIS_BACKUP_DIR/postgres/legal_rag.dump" \
  "$AEGIS_BACKUP_DIR"/qdrant/*.snapshot \
  > "$AEGIS_BACKUP_DIR/SHA256SUMS"
```

PostgreSQL's custom dump is intended for `pg_restore`; Qdrant's
[snapshot documentation](https://qdrant.tech/documentation/operations/snapshots/)
requires restore into the same minor or next minor Qdrant version. The raw
MinIO copy should be restored first into the same pinned MinIO release, then
upgraded separately.

A backup is not accepted until a restore drill succeeds on an isolated Docker
project/network and the restored counts, one object download, one search and
one role-isolation test pass. Never test restore by overwriting the live
volumes. Never use `docker compose down -v`; it deletes durable data.

## 10. Release and server rollback

### Before every change

- Record the Git commit, application version, Docker image versions, model name,
  corpus point counts and migration revision.
- Take the coordinated backup above.
- Keep the last accepted installers and checksums.
- Test database migrations and Qdrant compatibility on a clone first.

### Desktop-only fault

1. Stop distribution and leave/revert the faulty GitHub release to draft.
2. Existing Tauri clients cannot normally auto-downgrade by SemVer. Build the
   last known-good code as a **new higher patch version**, test it, then publish
   that corrective release.
3. For manual-update pilots, send the accepted previous installer with its
   original checksum, or the higher corrective build, to all four users.
4. Verify each device reports the accepted behavior before reopening work.

### Backend fault without data corruption

1. Put the service in maintenance and preserve logs.
2. Deploy the previously recorded backend image/commit only if its database
   schema is compatible with the current database.
3. Restart the backend and run health, role-isolation, source and Fast-latency
   checks before allowing clients back in.

Do not run an Alembic downgrade merely because code was rolled back. Use it only
when the specific migration has a tested reversible downgrade path.

### Data or migration fault

1. Stop the backend immediately to prevent further writes.
2. Preserve the damaged volumes for investigation.
3. Restore PostgreSQL, MinIO, Qdrant and `legal_kb` from the same coordinated
   backup into an isolated environment.
4. Verify counts, checksums, object downloads, retrieval, citations and RBAC.
5. Switch production only after acceptance; retain the damaged copy until the
   incident is understood.

After any rollback, rotate exposed credentials, revoke unknown Tailscale
devices, invalidate sessions if JWT secrets changed, document data loss against
the RPO, and run the complete four-role checklist.

## Go/no-go summary

For the **primary offline architecture**, release beyond a supervised technical
pilot only when:

- a clean machine can install, start, stop, migrate and recover the entire
  local stack without a repository checkout or manual Docker intervention;
- all service and inference ports are loopback-only and ordinary use succeeds
  with Wi-Fi/networking disabled;
- every device has a distinct local role/account, distinct secrets, a validated
  25,517-point corpus and zero cross-role API leakage;
- the application, backend, model and corpus versions are visible and their
  signed/checksummed update plus rollback paths have passed;
- each device has completed an encrypted backup and isolated restore drill;
- Fast p95 is below five seconds on each actual device; and
- macOS and Windows packages pass their native signing/trust checks.

Until the sidecar/bootstrap and clean-machine gates pass, call the result a
**supervised developer pilot**, not a self-contained offline desktop release.

For **Alternative B (shared Tailscale host)**, release only when:

- the host is loopback-bound and only private TLS port 443 is granted;
- all four named Tailscale identities and application roles are distinct;
- each installer contains the correct stable tailnet API URL;
- hashes, updater signatures and OS signatures/notarization are verified;
- backup plus isolated restore drill has passed;
- Fast p95 is below five seconds on the actual four-device path;
- cross-user and cross-role isolation tests show zero leakage; and
- every user knows that this is decision support, not legal advice, and that
  the single host creates planned/unplanned downtime.

Anything else is a supervised local demo, not an accepted four-user release.
