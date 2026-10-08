#!/usr/bin/env bash
set -euo pipefail

BASE_IMAGE="${LINUX_IMAGE:-ubuntu:latest}"
SERVER_IMAGE="${SERVER_IMAGE:-codex-linux-server:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-codex-linux-server}"
HOST_PORT="${HOST_PORT:-8080}"
DATA_VOLUME="${DATA_VOLUME:-codex-security-data}"
SESSION_SECRET_FILE="${SESSION_SECRET_FILE:-secrets/session_secret}"
WEBAUTHN_BOOTSTRAP_TOKEN_FILE="${WEBAUTHN_BOOTSTRAP_TOKEN_FILE:-secrets/webauthn_bootstrap_token}"
DATA_ENCRYPTION_KEY_FILE="${DATA_ENCRYPTION_KEY_FILE:-secrets/data_encryption_key}"
CREATED_CONTAINER_ID=""
BUILD_TEMP_DIR=""

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
DATA_ENCRYPTION_KEY_SOURCE="$(resolve_secret_file "$DATA_ENCRYPTION_KEY_FILE")"

if [[ ! "${CONTAINER_NAME}" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]]; then
  echo "ERROR: CONTAINER_NAME must be a valid Docker container name." >&2
  exit 1
fi
if [[ ! "${HOST_PORT}" =~ ^[0-9]{1,5}$ ]] || (( 10#${HOST_PORT} < 1 || 10#${HOST_PORT} > 65535 )); then
  echo "ERROR: HOST_PORT must be an integer from 1 to 65535." >&2
  exit 1
fi

# Kept as a compatibility warning for callers of the old script. No value of
# this legacy flag permits removing either an existing or newly created container.
if [[ "${CLEANUP_AFTER_TEST:-false}" != "false" ]]; then
  echo "WARNING: CLEANUP_AFTER_TEST is ignored; all containers are retained." >&2
fi

report_retained_container() {
  if [[ -n "${BUILD_TEMP_DIR}" ]]; then
    rm -f -- "${BUILD_TEMP_DIR}/image-id"
    rmdir -- "${BUILD_TEMP_DIR}"
  fi
  if [[ -n "${CREATED_CONTAINER_ID}" ]]; then
    echo "Container retained: ${CREATED_CONTAINER_ID} (${CONTAINER_NAME})" >&2
    echo "Inspect with: docker container inspect ${CREATED_CONTAINER_ID}" >&2
  fi
}
trap report_retained_container EXIT

# A failed list is an error, not evidence that the name is available. Include
# stopped containers and compare literal names before pulling or building.
if ! existing_names="$(docker ps -a --format '{{.Names}}')"; then
  echo "ERROR: Could not list containers; nothing will be created or replaced." >&2
  exit 1
fi
while IFS= read -r existing_name; do
  if [[ "${existing_name}" == "${CONTAINER_NAME}" ]]; then
    echo "ERROR: Container ${CONTAINER_NAME} already exists; it has not been changed." >&2
    echo "Use a different CONTAINER_NAME, unused HOST_PORT, and separate DATA_VOLUME for a parallel deployment." >&2
    exit 1
  fi
done <<< "${existing_names}"

echo "==> Pulling base Linux image: ${BASE_IMAGE}"
docker pull "${BASE_IMAGE}"

echo "==> Building WebAuthn-protected container server image: ${SERVER_IMAGE}"
BUILD_TEMP_DIR="$(mktemp -d)"
docker build \
  --iidfile "${BUILD_TEMP_DIR}/image-id" \
  --pull \
  --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
  -t "${SERVER_IMAGE}" \
  .

# Use the result of this build, never a mutable tag that another build can move.
BUILT_IMAGE_ID="$(cat "${BUILD_TEMP_DIR}/image-id")"
if [[ ! "${BUILT_IMAGE_ID}" =~ ^sha256:[a-f0-9]{64}$ ]]; then
  echo "ERROR: Docker did not return a valid image ID; no container will be created." >&2
  exit 1
fi

echo "==> Creating persistent WebAuthn credential volume: ${DATA_VOLUME}"
docker volume create "${DATA_VOLUME}" >/dev/null

echo "==> Starting security-key protected server on 127.0.0.1:${HOST_PORT}"
CREATED_CONTAINER_ID="$(docker create \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  -p "127.0.0.1:${HOST_PORT}:8080" \
  -v "${DATA_VOLUME}:/data" \
  --mount "type=bind,src=${SESSION_SECRET_SOURCE},dst=/run/secrets/session_secret,readonly" \
  --mount "type=bind,src=${BOOTSTRAP_TOKEN_SOURCE},dst=/run/secrets/webauthn_bootstrap_token,readonly" \
  --mount "type=bind,src=${DATA_ENCRYPTION_KEY_SOURCE},dst=/run/secrets/data_encryption_key,readonly" \
  -e "SESSION_SECRET_FILE=/run/secrets/session_secret" \
  -e "WEBAUTHN_BOOTSTRAP_TOKEN_FILE=/run/secrets/webauthn_bootstrap_token" \
  -e "DATA_ENCRYPTION_KEY_FILE=/run/secrets/data_encryption_key" \
  -e "WEBAUTHN_RP_ID=${WEBAUTHN_RP_ID}" \
  -e "WEBAUTHN_ORIGIN=${WEBAUTHN_ORIGIN}" \
  -e "WEBAUTHN_RP_NAME=${WEBAUTHN_RP_NAME:-Codex Container Server}" \
  "${BUILT_IMAGE_ID}")"
if [[ ! "${CREATED_CONTAINER_ID}" =~ ^[a-f0-9]{64}$ ]]; then
  echo "ERROR: Docker did not return a valid container ID; no container will be started." >&2
  exit 1
fi
# Reserve the name atomically, then address only this invocation's container.
docker start "${CREATED_CONTAINER_ID}" >/dev/null

echo "==> Waiting for /healthz"
for attempt in {1..45}; do
  if docker exec "${CREATED_CONTAINER_ID}" curl --connect-timeout 2 --max-time 5 -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1; then
    echo "Container health endpoint: OK"
    break
  fi

  if [[ "${attempt}" -eq 45 ]]; then
    echo "ERROR: Container server did not become healthy; it has been retained for inspection." >&2
    docker logs "${CREATED_CONTAINER_ID}" >&2 || true
    exit 1
  fi
  sleep 1
done

echo "==> Verifying WebAuthn protection"
docker exec "${CREATED_CONTAINER_ID}" curl --connect-timeout 2 --max-time 5 -fsS http://127.0.0.1:8080/ | grep -q "Security Key Required"
docker exec "${CREATED_CONTAINER_ID}" curl --connect-timeout 2 --max-time 5 -fsS http://127.0.0.1:8080/api/security/status | grep -q '"security_key_required":true'
docker exec "${CREATED_CONTAINER_ID}" sh -lc '
  set -eu
  headers="$(curl --connect-timeout 2 --max-time 5 -fsSI http://127.0.0.1:8080/)"
  printf "%s\n" "$headers" | tr -d "\r" | grep -qi "^X-Frame-Options: DENY$"
'

echo "==> Verifying bootstrap registration controls"
docker exec "${CREATED_CONTAINER_ID}" sh -lc '
  set -eu
  code="$(curl --connect-timeout 2 --max-time 5 -sS -o /tmp/no-bootstrap.json -w "%{http_code}" -X POST -H "Content-Type: application/json" -d "{}" http://127.0.0.1:8080/api/security/register/options)"
  test "$code" = "403"
'
docker exec "${CREATED_CONTAINER_ID}" sh -lc '
  set -eu
  token="$(cat "$WEBAUTHN_BOOTSTRAP_TOKEN_FILE")"
  code="$(curl --connect-timeout 2 --max-time 5 -sS -o /tmp/bootstrap-options.json -w "%{http_code}" -X POST -H "Content-Type: application/json" -H "X-Bootstrap-Token: $token" -d "{}" http://127.0.0.1:8080/api/security/register/options)"
  test "$code" = "200"
  grep -q "\"challenge\"" /tmp/bootstrap-options.json
'

echo "==> Container status"
docker ps --filter "id=${CREATED_CONTAINER_ID}"

echo
echo "Container server deployment: OK"
echo "WebAuthn security-key gate: ENABLED"
echo "Secret transport: FILE MOUNTS"
echo "Private-data encryption: AES-256-GCM"
echo "Local URL: http://127.0.0.1:${HOST_PORT}"
