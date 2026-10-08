#!/usr/bin/env bash
set -euo pipefail

IMAGE="${LINUX_IMAGE:-ubuntu:latest}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is required but was not found." >&2
  exit 1
fi

echo "==> Pulling latest Linux image: ${IMAGE}"
docker pull "${IMAGE}"

# Capture the local image identity once; later tag movement cannot change run.
IMAGE_ID="$(docker image inspect "${IMAGE}" --format '{{.Id}}')"
if [[ ! "${IMAGE_ID}" =~ ^sha256:[a-f0-9]{64}$ ]]; then
  echo "ERROR: Docker did not return a valid image ID; no container will be run." >&2
  exit 1
fi

echo "==> Image digest"
docker image inspect "${IMAGE_ID}" --format '{{join .RepoDigests "\n"}}'

echo "==> Running smoke test inside ${IMAGE}"
docker run "${IMAGE_ID}" sh -lc '
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

echo "Smoke-test container retained; automatic container cleanup is disabled."
