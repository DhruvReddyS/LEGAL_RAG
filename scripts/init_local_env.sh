#!/usr/bin/env bash
# Create .env from .env.example and fill every CHANGE_ME value.
#
# start_local.sh refuses to run while a CHANGE_ME remains, and the four in
# .env.example are local-only secrets: two JWT signing keys and the MinIO root
# user and password that compose creates from them. Any values work provided
# the password is at least 8 characters, so generating them beats asking
# someone to invent four strings by hand on a first run.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

if test -f "$ENV_FILE"; then
  printf 'Keeping the existing .env. Delete it first to regenerate.\n'
  grep -c CHANGE_ME "$ENV_FILE" >/dev/null 2>&1 && {
    printf 'It still contains CHANGE_ME values:\n'
    grep -n CHANGE_ME "$ENV_FILE" || true
  }
  exit 0
fi

cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"

python3 - "$ENV_FILE" <<'PY'
import pathlib
import secrets
import sys

path = pathlib.Path(sys.argv[1])
lines = []
for line in path.read_text(encoding="utf-8").splitlines():
    key = line.split("=", 1)[0]
    if line.endswith("=CHANGE_ME"):
        if key.startswith("JWT"):
            line = f"{key}={secrets.token_urlsafe(48)}"
        elif key == "S3_ACCESS_KEY_ID":
            line = f"{key}=localminioadmin"
        elif key == "S3_SECRET_ACCESS_KEY":
            line = f"{key}={secrets.token_urlsafe(24)}"
    lines.append(line)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")

remaining = sum(1 for line in lines if "CHANGE_ME" in line)
if remaining:
    # A new CHANGE_ME in .env.example that this script does not know about
    # must be reported, not left for start_local.sh to reject later.
    print(f"{remaining} CHANGE_ME value(s) still need filling by hand:")
    for line in lines:
        if "CHANGE_ME" in line:
            print(f"  {line.split('=', 1)[0]}")
    raise SystemExit(1)
print("Wrote .env with generated local secrets.")
PY

printf 'Next: open Docker Desktop, then run ./scripts/start_local.sh 3000\n'
