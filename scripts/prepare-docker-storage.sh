#!/usr/bin/env bash
# Create/reuse a persistent Docker-managed logical volume, not a disk partition.
set -euo pipefail

volume="${DATA_VOLUME:-codex-security-data}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI not found; install Docker Engine first." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Cannot access Docker daemon; check service and permissions." >&2
  exit 1
fi
if [[ ! "$volume" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
  echo "DATA_VOLUME must be a valid named volume identifier." >&2
  exit 1
fi

echo "==> Ensuring persistent Docker volume: ${volume}"
docker volume create --driver local \
  --label "io.github.koreatest12.codex.role=persistent-data" \
  "$volume" >/dev/null
docker volume inspect "$volume" --format 'Name={{.Name}} Driver={{.Driver}} Mountpoint={{.Mountpoint}}'
echo "The volume retains SQLite/WebAuthn records across image rebuilds."
echo "Never run 'docker compose down -v' unless permanent data loss is intended."
echo "This is not a new physical disk, partition, or storage quota."
