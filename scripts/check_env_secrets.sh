#!/usr/bin/env bash
# Refuse to start on an .env that still holds a CHANGE_ME value.
#
# Usage: check_env_secrets.sh <path-to-env-file>
set -euo pipefail

ENV_FILE="${1:?usage: check_env_secrets.sh <env-file>}"
placeholders="$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=.*CHANGE_ME' "$ENV_FILE" | cut -d= -f1 || true)"
if test -n "$placeholders"; then
  printf 'These values in %s are still placeholders:\n' "$ENV_FILE" >&2
  printf '  %s\n' $placeholders >&2
  printf 'Run ./scripts/init_local_env.sh on a fresh checkout, or fill them in by hand.\n' >&2
  exit 1
fi
