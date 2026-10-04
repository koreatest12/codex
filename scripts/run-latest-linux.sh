#!/usr/bin/env bash
set -euo pipefail

IMAGE="${LINUX_IMAGE:-ubuntu:latest}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is required but was not found." >&2
  exit 1
fi

echo "==> Pulling latest Linux image: ${IMAGE}"
docker pull "${IMAGE}"

echo "==> Image digest"
docker image inspect "${IMAGE}" --format '{{join .RepoDigests "\n"}}'

echo "==> Running smoke test inside ${IMAGE}"
docker run --rm "${IMAGE}" sh -lc '
  set -eu
  echo "--- /etc/os-release ---"
  cat /etc/os-release
  echo
  echo "--- architecture ---"
  dpkg --print-architecture 2>/dev/null || uname -m
  echo
  echo "--- kernel ---"
  uname -a
  echo
  echo "Linux image smoke test: OK"
'
