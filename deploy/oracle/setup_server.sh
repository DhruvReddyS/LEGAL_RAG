#!/usr/bin/env bash
# Run once on the Oracle server, from the repository root:
#   PUBLIC_HOST=<public-ip-with-dashes>.sslip.io ./deploy/oracle/setup_server.sh
set -euo pipefail

: "${PUBLIC_HOST:?set PUBLIC_HOST, for example 1-2-3-4.sslip.io}"
[ "$(uname -m)" = "aarch64" ] || echo "Note: this was written for an ARM server, and this is $(uname -m)."

if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install --yes docker.io docker-compose-v2
  sudo usermod -aG docker "$USER"
fi

# Oracle's Ubuntu image blocks these ports in its own firewall as well as in the console.
sudo iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 5 -p tcp --dport 80 -j ACCEPT
sudo iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 5 -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true

[ -f .env ] || ./scripts/init_local_env.sh
export PUBLIC_HOST
sudo -E docker compose --env-file .env -f docker/docker-compose.yml -f deploy/oracle/docker-compose.oracle.yml up -d --build
echo "Started. Check: curl https://${PUBLIC_HOST}/health"
