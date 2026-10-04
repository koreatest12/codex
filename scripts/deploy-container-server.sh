#!/usr/bin/env bash
set -euo pipefail

BASE_IMAGE="${LINUX_IMAGE:-ubuntu:latest}"
SERVER_IMAGE="${SERVER_IMAGE:-codex-linux-server:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-codex-linux-server}"
HOST_PORT="${HOST_PORT:-8080}"
DATA_VOLUME="${DATA_VOLUME:-codex-security-data}"
SESSION_SECRET_FILE="${SESSION_SECRET_FILE:-secrets/session_secret}"
WEBAUTHN_BOOTSTRAP_TOKEN_FILE="${WEBAUTHN_BOOTSTRAP_TOKEN_FILE:-secrets/webauthn_bootstrap_token}"
CLEANUP_AFTER_TEST="${CLEANUP_AFTER_TEST:-false}"

: "${WEBAUTHN_RP_ID:?WEBAUTHN_RP_ID must be configured}"
: "${WEBAUTHN_ORIGIN:?WEBAUTHN_ORIGIN must be configured}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is required but was not found." >&2
  exit 1
fi

resolve_secret_file() {
  local path="$1"
  if [[ ! -f "$path" || ! -s "$path" ]]; then
    echo "ERROR: required secret file is missing or empty: $path" >&2
    exit 1
  fi
  local dir base
  dir="$(cd "$(dirname "$path")" && pwd -P)"
  base="$(basename "$path")"
  printf '%s/%s\n' "$dir" "$base"
}

SESSION_SECRET_SOURCE="$(resolve_secret_file "$SESSION_SECRET_FILE")"
BOOTSTRAP_TOKEN_SOURCE="$(resolve_secret_file "$WEBAUTHN_BOOTSTRAP_TOKEN_FILE")"

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
  --mount "type=bind,src=${SESSION_SECRET_SOURCE},dst=/run/secrets/session_secret,readonly" \
  --mount "type=bind,src=${BOOTSTRAP_TOKEN_SOURCE},dst=/run/secrets/webauthn_bootstrap_token,readonly" \
  -e "SESSION_SECRET_FILE=/run/secrets/session_secret" \
  -e "WEBAUTHN_BOOTSTRAP_TOKEN_FILE=/run/secrets/webauthn_bootstrap_token" \
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
docker exec "${CONTAINER_NAME}" sh -lc 'curl -fsSI http://127.0.0.1:8080/ | tr -d "\r" | grep -qi "^X-Frame-Options: DENY$"'

echo "==> Verifying bootstrap registration controls"
docker exec "${CONTAINER_NAME}" sh -lc '
  code="$(curl -sS -o /tmp/no-bootstrap.json -w "%{http_code}" -X POST -H "Content-Type: application/json" -d "{}" http://127.0.0.1:8080/api/security/register/options)"
  test "$code" = "403"
'
docker exec "${CONTAINER_NAME}" sh -lc '
  token="$(cat "$WEBAUTHN_BOOTSTRAP_TOKEN_FILE")"
  code="$(curl -sS -o /tmp/bootstrap-options.json -w "%{http_code}" -X POST -H "Content-Type: application/json" -H "X-Bootstrap-Token: $token" -d "{}" http://127.0.0.1:8080/api/security/register/options)"
  test "$code" = "200"
  grep -q "\"challenge\"" /tmp/bootstrap-options.json
'

echo "==> Container status"
docker ps --filter "name=^${CONTAINER_NAME}$"

echo
echo "Container server deployment: OK"
echo "WebAuthn security-key gate: ENABLED"
echo "Secret transport: FILE MOUNTS"
echo "Local URL: http://127.0.0.1:${HOST_PORT}"
