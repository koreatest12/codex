#!/usr/bin/env bash
# Create/reuse a persistent logical Docker volume; do not format host disks.
set -euo pipefail

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is unavailable; install/start Docker Engine first." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required to read the effective Compose volume name." >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$repo_root"

if [[ "${1:-}" == "--manual" ]]; then
  # Preserve the default volume used by scripts/deploy-container-server.sh.
  volume="${DATA_VOLUME:-codex-security-data}"
else
  # Respect an existing Compose project name and volume identity.
  if ! config="$(docker compose config --format json)"; then
    echo "Generate .env and secrets first, then rerun this command." >&2
    exit 1
  fi
  volume="$(printf '%s' "$config" | python3 -c \
    'import json,sys; print(json.load(sys.stdin)["volumes"]["security-data"]["name"])')"
fi

if [[ ! "$volume" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "Resolved volume name is invalid: $volume" >&2
  exit 1
fi

echo "==> Ensuring persistent Docker volume: $volume"
docker volume create --driver local \
  --label "io.github.koreatest12.codex.role=persistent-data" \
  "$volume" >/dev/null
docker volume inspect "$volume" --format 'Name={{.Name}} Driver={{.Driver}} Mountpoint={{.Mountpoint}}'
echo "Saved SQLite and WebAuthn data is retained across image rebuilds."
echo "Do NOT run docker compose down -v or docker volume rm unless intentional."
echo "This creates no physical partition and reserves no specific capacity."
