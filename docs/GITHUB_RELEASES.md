# GitHub Desktop Release Runbook

The desktop release workflow builds Tauri v2 installers for macOS arm64,
macOS x64, and Windows x64. It creates a **draft** GitHub Release containing
the platform installers, signed updater artifacts, signatures, and
`latest.json`. It never publishes a release automatically.

## Required repository secrets

Generate one long-lived Tauri updater key pair and protect the private key.
Existing installations trust this key, so losing or replacing it prevents them
from accepting future updates.

- `TAURI_SIGNING_PRIVATE_KEY`: complete private updater key contents. Required.
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`: private-key password. Required only
  when the generated key is encrypted; otherwise it may be left unset.
- `TAURI_UPDATER_PUBLIC_KEY`: complete public updater key contents. Required.
  This value is not confidential, but storing it beside the paired private-key
  secret makes release-key rotation explicit and prevents an accidental
  mismatch between the updater artifacts and the application configuration.

Generate the pair locally from `frontend/`:

```bash
npm run tauri signer generate -- -w "$HOME/.tauri/aegis-updater.key"
```

Store the private-key contents and password as GitHub Actions secrets. The
corresponding public key is safe to place in the Tauri updater configuration;
never commit or paste the private key into `.env`, YAML, source code, logs, or
release assets.

During each build, the workflow writes a mode-`0600` temporary Tauri override
containing the public key and an endpoint derived from GitHub's trusted
`GITHUB_REPOSITORY` context:

```text
https://github.com/<owner>/<repository>/releases/latest/download/latest.json
```

The temporary file exists only on the disposable GitHub runner and is not
committed. The private updater key is passed only as a masked process
environment variable.

## Optional production macOS signing and notarization secrets

Unsigned/ad-hoc builds are suitable for local capstone testing. External macOS
distribution requires an Apple Developer ID certificate and notarization.

- `APPLE_CERTIFICATE`: base64-encoded Developer ID Application `.p12`.
- `APPLE_CERTIFICATE_PASSWORD`: password used when exporting the `.p12`.
- `APPLE_SIGNING_IDENTITY`: exact Developer ID Application identity.
- `APPLE_ID`: Apple developer account email.
- `APPLE_PASSWORD`: app-specific Apple password, not the account password.
- `APPLE_TEAM_ID`: Apple Developer Team ID.

Preview CI deliberately leaves these variables unset so Tauri uses the
configured ad-hoc identity. After a valid certificate is available, add a
dedicated macOS signing/import step and map these secrets only into macOS jobs;
then configure the Tauri bundle identity for Developer ID signing.

Windows Authenticode signing is not enabled by this foundation. The updater
artifacts are cryptographically signed by the Tauri updater key, but public
Windows distribution should later add a trusted code-signing certificate or
Azure Key Vault signing configuration.

## Release procedure

1. Set the same SemVer value in `frontend/package.json`,
   `frontend/package-lock.json`, `frontend/src-tauri/tauri.conf.json`,
   `frontend/src-tauri/Cargo.toml`, and the desktop entry in `Cargo.lock`.
2. Validate locally:

   ```bash
   python3 scripts/check_release_version.py --tag v0.3.0
   ```

3. Push the matching `v<version>` tag, or run **Desktop release** manually with
   that tag. The workflow rejects mismatched or malformed versions.
4. Wait for backend tests, frontend lint/static build, and all three native
   build jobs to pass.
5. Open the draft release and verify the installers, `.sig` files, updater
   archives, and `latest.json` entries for `darwin-aarch64`, `darwin-x86_64`,
   and `windows-x86_64`.
6. Smoke-test installers on the target operating systems. Publish the draft
   manually only after acceptance.

`GITHUB_TOKEN` is supplied automatically by GitHub Actions. The build jobs have
release-write permission; the validation job is read-only, and checkout does
not persist credentials.
