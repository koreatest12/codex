#!/usr/bin/env bash
set -euo pipefail

BASE_IMAGE="${LINUX_IMAGE:-ubuntu:latest}"
SERVER_IMAGE="${SERVER_IMAGE:-codex-linux-server:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-codex-linux-server}"
HOST_PORT="${HOST_PORT:-8080}"
CLEANUP_AFTER_TEST="${CLEANUP_AFTER_TEST:-false}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is required but was not found." >&2
  exit 1
fi

cleanup() {
  if [[ "${CLEANUP_AFTER_TEST}" == "true" ]]; then
    docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "==> Pulling base Linux image: ${BASE_IMAGE}"
docker pull "${BASE_IMAGE}"

echo "==> Building container server image: ${SERVER_IMAGE}"
docker build \
  --pull \
  --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
  -t "${SERVER_IMAGE}" \
  .

echo "==> Replacing existing container if present: ${CONTAINER_NAME}"
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

echo "==> Starting container server on 127.0.0.1:${HOST_PORT}"
docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  -p "127.0.0.1:${HOST_PORT}:8080" \
  "${SERVER_IMAGE}"

echo "==> Waiting for /healthz"
for attempt in {1..30}; do
  if docker exec "${CONTAINER_NAME}" curl -fsS http://127.0.0.1:8080/healthz >/dev/null; then
    echo "Container health endpoint: OK"
    break
  fi

  if [[ "${attempt}" -eq 30 ]]; then
    echo "ERROR: Container server did not become healthy." >&2
    docker logs "${CONTAINER_NAME}" >&2 || true
    exit 1
  fi

  sleep 1
done

echo "==> Verifying web page"
docker exec "${CONTAINER_NAME}" curl -fsS http://127.0.0.1:8080/ | grep -q "Codex Linux Container Server"

echo "==> Container status"
docker ps --filter "name=^${CONTAINER_NAME}$"

echo
echo "Container server deployment: OK"
echo "Local URL: http://127.0.0.1:${HOST_PORT}"
