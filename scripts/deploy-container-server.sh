#!/usr/bin/env bash
set -euo pipefail

BASE_IMAGE="${LINUX_IMAGE:-ubuntu:latest}"
SERVER_IMAGE="${SERVER_IMAGE:-codex-linux-server:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-codex-linux-server}"
HOST_PORT="${HOST_PORT:-8080}"
CREATED_CONTAINER_ID=""

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is required but was not found." >&2
  exit 1
fi

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
    echo "Use a different CONTAINER_NAME and an unused HOST_PORT for a separate deployment." >&2
    exit 1
  fi
done <<< "${existing_names}"

echo "==> Pulling base Linux image: ${BASE_IMAGE}"
docker pull "${BASE_IMAGE}"

echo "==> Building container server image: ${SERVER_IMAGE}"
docker build \
  --pull \
  --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
  -t "${SERVER_IMAGE}" \
  .

# Docker atomically reserves the name during create. A concurrent creator wins
# safely: this command fails rather than replacing or attaching to its container.
echo "==> Creating a new container server on 127.0.0.1:${HOST_PORT}"
CREATED_CONTAINER_ID="$(docker create \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  -p "127.0.0.1:${HOST_PORT}:8080" \
  "${SERVER_IMAGE}")"
if [[ ! "${CREATED_CONTAINER_ID}" =~ ^[a-f0-9]{64}$ ]]; then
  echo "ERROR: Docker did not return a valid container ID; no container will be started." >&2
  exit 1
fi

# From here on, address only the ID returned by this invocation. Never look up
# the name again: another process could have removed/reused it in the meantime.
docker start "${CREATED_CONTAINER_ID}" >/dev/null

echo "==> Waiting for /healthz"
for attempt in {1..30}; do
  if docker exec "${CREATED_CONTAINER_ID}" curl -fsS http://127.0.0.1:8080/healthz >/dev/null; then
    echo "Container health endpoint: OK"
    break
  fi

  if [[ "${attempt}" -eq 30 ]]; then
    echo "ERROR: Container server did not become healthy; it has been retained for inspection." >&2
    docker logs "${CREATED_CONTAINER_ID}" >&2 || true
    exit 1
  fi

  sleep 1
done

echo "==> Verifying web page"
docker exec "${CREATED_CONTAINER_ID}" curl -fsS http://127.0.0.1:8080/ | grep -q "Codex Linux Container Server"

echo "==> Container status"
docker ps --filter "id=${CREATED_CONTAINER_ID}"

echo
echo "Container server deployment: OK"
echo "Local URL: http://127.0.0.1:${HOST_PORT}"
