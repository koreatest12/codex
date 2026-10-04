#!/usr/bin/env bash
set -euo pipefail

BASE_IMAGE="${LINUX_IMAGE:-ubuntu:latest}"
SERVER_IMAGE="${SERVER_IMAGE:-codex-linux-server:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-codex-linux-server}"
HOST_PORT="${HOST_PORT:-8080}"
DATA_VOLUME="${DATA_VOLUME:-codex-security-data}"
CLEANUP_AFTER_TEST="${CLEANUP_AFTER_TEST:-false}"

: "${SESSION_SECRET:?SESSION_SECRET must be configured}"
: "${WEBAUTHN_BOOTSTRAP_TOKEN:?WEBAUTHN_BOOTSTRAP_TOKEN must be configured}"
: "${WEBAUTHN_RP_ID:?WEBAUTHN_RP_ID must be configured}"
: "${WEBAUTHN_ORIGIN:?WEBAUTHN_ORIGIN must be configured}"

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

echo "==> Building WebAuthn-protected container server image: ${SERVER_IMAGE}"
docker build \
  --pull \
  --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
  -t "${SERVER_IMAGE}" \
  .

echo "==> Creating persistent WebAuthn credential volume: ${DATA_VOLUME}"
docker volume create "${DATA_VOLUME}" >/dev/null

echo "==> Replacing existing container if present: ${CONTAINER_NAME}"
docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

echo "==> Starting security-key protected server on 127.0.0.1:${HOST_PORT}"
docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  -p "127.0.0.1:${HOST_PORT}:8080" \
  -v "${DATA_VOLUME}:/data" \
  -e "SESSION_SECRET=${SESSION_SECRET}" \
  -e "WEBAUTHN_BOOTSTRAP_TOKEN=${WEBAUTHN_BOOTSTRAP_TOKEN}" \
  -e "WEBAUTHN_RP_ID=${WEBAUTHN_RP_ID}" \
  -e "WEBAUTHN_ORIGIN=${WEBAUTHN_ORIGIN}" \
  -e "WEBAUTHN_RP_NAME=${WEBAUTHN_RP_NAME:-Codex Container Server}" \
  "${SERVER_IMAGE}"

echo "==> Waiting for /healthz"
for attempt in {1..45}; do
  if docker exec "${CONTAINER_NAME}" curl -fsS http://127.0.0.1:8080/healthz >/dev/null; then
    echo "Container health endpoint: OK"
    break
  fi

  if [[ "${attempt}" -eq 45 ]]; then
    echo "ERROR: Container server did not become healthy." >&2
    docker logs "${CONTAINER_NAME}" >&2 || true
    exit 1
  fi

  sleep 1
done

echo "==> Verifying WebAuthn protection"
docker exec "${CONTAINER_NAME}" curl -fsS http://127.0.0.1:8080/ | grep -q "Security Key Required"
docker exec "${CONTAINER_NAME}" curl -fsS http://127.0.0.1:8080/api/security/status | grep -q '"security_key_required":true'
docker exec "${CONTAINER_NAME}" sh -lc "curl -fsSI http://127.0.0.1:8080/ | tr -d '\r' | grep -qi '^X-Frame-Options: DENY$'"

echo "==> Container status"
docker ps --filter "name=^${CONTAINER_NAME}$"

echo
echo "Container server deployment: OK"
echo "WebAuthn security-key gate: ENABLED"
echo "Local URL: http://127.0.0.1:${HOST_PORT}"
