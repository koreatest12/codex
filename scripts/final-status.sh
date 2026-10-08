#!/usr/bin/env bash
# Final operational summary without dumping account credentials or Docker secrets.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "STATUS=UNAVAILABLE reason=Docker-daemon-not-accessible"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "STATUS=UNAVAILABLE reason=Docker-Compose-not-installed"
  exit 1
fi

mode="FIDO2-only"
compose_files=(-f compose.yaml)
if [[ -s secrets/admin_account ]]; then
  echo "ADMIN_ACCOUNT_PROVISIONED=yes (credentials never printed)"
  compose_files+=(-f compose.account.yaml)
  mode="Password+FIDO2 (account overlay selected)"
else
  echo "ADMIN_ACCOUNT_PROVISIONED=no"
fi

echo "AUTH_REQUESTED=$mode"
echo "==> Running containers"
docker compose "${compose_files[@]}" ps
echo "==> Built images"
docker compose "${compose_files[@]}" images || true
echo "==> Persistent storage"
docker compose "${compose_files[@]}" config --format json |
  python3 -c 'import json,sys; c=json.load(sys.stdin); print("VOLUME="+str(c["volumes"]["security-data"]["name"]))'

echo "==> Health endpoint"
port="$(docker compose "${compose_files[@]}" port web 8080 2>/dev/null || true)"
if [[ -z "$port" ]]; then
  echo "STATUS=STOPPED reason=No-published-container-port"
  exit 1
fi
port_number="${port##*:}"
if ! [[ "$port_number" =~ ^[0-9]+$ ]]; then
  echo "STATUS=UNKNOWN reason=Unable-to-resolve-container-port"
  exit 1
fi
if curl -fsS --max-time 5 "http://127.0.0.1:${port_number}/healthz"; then
  echo
  echo "STATUS=HEALTHY (Nginx-to-Flask health check only)"
  echo "Protected status: log in and open /api/system/status"
else
  echo "STATUS=UNHEALTHY"
  exit 1
fi
