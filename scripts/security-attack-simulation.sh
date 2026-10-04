#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-codex-linux-server}"
HOST_PORT="${HOST_PORT:-8080}"
SESSION_SECRET_FILE="${SESSION_SECRET_FILE:-secrets/session_secret}"
WEBAUTHN_BOOTSTRAP_TOKEN_FILE="${WEBAUTHN_BOOTSTRAP_TOKEN_FILE:-secrets/webauthn_bootstrap_token}"
DATA_ENCRYPTION_KEY_FILE="${DATA_ENCRYPTION_KEY_FILE:-secrets/data_encryption_key}"
BASE_URL="http://127.0.0.1:${HOST_PORT}"

fail() {
  echo "SECURITY TEST FAILED: $*" >&2
  exit 1
}

require_file() {
  [[ -s "$1" ]] || fail "missing secret canary file: $1"
}

require_file "${SESSION_SECRET_FILE}"
require_file "${WEBAUTHN_BOOTSTRAP_TOKEN_FILE}"
require_file "${DATA_ENCRYPTION_KEY_FILE}"

SESSION_CANARY="$(cat "${SESSION_SECRET_FILE}")"
BOOTSTRAP_CANARY="$(cat "${WEBAUTHN_BOOTSTRAP_TOKEN_FILE}")"
DATA_KEY_CANARY="$(cat "${DATA_ENCRYPTION_KEY_FILE}")"

assert_secret_absent() {
  local label="$1"
  local content="$2"
  if printf '%s' "$content" | grep -Fq "${SESSION_CANARY}"; then
    fail "session secret leaked through ${label}"
  fi
  if printf '%s' "$content" | grep -Fq "${BOOTSTRAP_CANARY}"; then
    fail "bootstrap token leaked through ${label}"
  fi
  if printf '%s' "$content" | grep -Fq "${DATA_KEY_CANARY}"; then
    fail "data encryption key leaked through ${label}"
  fi
}

echo "==> Simulated attack: inspect container environment"
inspect_env="$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${CONTAINER_NAME}")"
assert_secret_absent "docker inspect environment" "${inspect_env}"
printf '%s\n' "${inspect_env}" | grep -q '^SESSION_SECRET_FILE=' || fail "secret file path is not configured"

echo "==> Simulated attack: read process environment"
runtime_env="$(docker exec "${CONTAINER_NAME}" env)"
assert_secret_absent "container process environment" "${runtime_env}"

echo "==> Simulated attack: scrape public HTTP responses"
for path in / /healthz /api/security/status /api/private-values /static/security.js /static/security.css /.env /secrets/session_secret /secrets/data_encryption_key /run/secrets/session_secret /run/secrets/data_encryption_key /data/webauthn.db '/%2e%2e/%2e%2e/run/secrets/data_encryption_key'; do
  response="$(curl -sS --max-time 5 "${BASE_URL}${path}" || true)"
  assert_secret_absent "HTTP ${path}" "${response}"
done

echo "==> Simulated attack: unauthorized registration attempts"
code="$(curl -sS -o /tmp/no-token.json -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' "${BASE_URL}/api/security/register/options")"
[[ "${code}" == "403" ]] || fail "registration without token returned HTTP ${code}"

code="$(curl -sS -o /tmp/wrong-token.json -w '%{http_code}' -X POST -H 'Content-Type: application/json' -H 'X-Bootstrap-Token: definitely-not-the-token' -d '{}' "${BASE_URL}/api/security/register/options")"
[[ "${code}" == "403" ]] || fail "registration with wrong token returned HTTP ${code}"

echo "==> Simulated attack: enumerate registered keys without authentication"
code="$(curl -sS -o /tmp/credentials.json -w '%{http_code}' "${BASE_URL}/api/security/credentials")"
[[ "${code}" == "403" ]] || fail "credential metadata endpoint returned HTTP ${code} without authentication"

echo "==> Simulated attack: private-value enumeration without authentication"
code="$(curl -sS -o /tmp/private-values.json -w '%{http_code}' "${BASE_URL}/api/private-values")"
[[ "${code}" == "403" ]] || fail "private-value endpoint returned HTTP ${code} without authentication"

echo "==> Simulated attack: inspect application logs"
container_logs="$(docker logs "${CONTAINER_NAME}" 2>&1 || true)"
assert_secret_absent "container logs" "${container_logs}"

echo "==> Verify server stores no WebAuthn private-key column"
schema="$(docker exec "${CONTAINER_NAME}" /opt/venv/bin/python -c 'import sqlite3; c=sqlite3.connect("/data/webauthn.db"); print(",".join(r[1] for r in c.execute("PRAGMA table_info(credentials)")))' )"
printf '%s' "${schema}" | grep -q 'public_key' || fail "public key column missing"
if printf '%s' "${schema}" | grep -Eq '(^|,)(private_key|secret_key|private_key_material)(,|$)'; then
  fail "private-key material column exists in WebAuthn database"
fi

echo "==> Verify encrypted private-data schema contains no plaintext value column"
private_schema="$(docker exec "${CONTAINER_NAME}" /opt/venv/bin/python -c 'import sqlite3; c=sqlite3.connect("/data/webauthn.db"); print(",".join(r[1] for r in c.execute("PRAGMA table_info(private_values)")))' )"
printf '%s' "${private_schema}" | grep -q 'ciphertext' || fail "encrypted ciphertext column missing"
printf '%s' "${private_schema}" | grep -q 'nonce' || fail "AES-GCM nonce column missing"
if printf '%s' "${private_schema}" | grep -Eq '(^|,)(value|plaintext|reservation_number|phone|email)(,|$)'; then
  fail "plaintext private-data column exists"
fi

echo
echo "SIMULATED ATTACK RESULT: PASS"
echo "- HTTP attacker could not retrieve canary secrets."
echo "- Wrong/missing bootstrap tokens were rejected."
echo "- Unauthenticated credential enumeration was rejected."
echo "- docker inspect/process environment did not contain secret values."
echo "- Application logs did not contain secret values."
echo "- Data encryption key did not appear in HTTP, logs, inspect output, or process environment."
echo "- Private-data API rejected unauthenticated enumeration."
echo "- Private values are stored as AES-GCM nonce/ciphertext rather than plaintext columns."
echo "- WebAuthn database schema stores public keys, not hardware private keys."
echo "NOTE: host root/Docker-daemon compromise remains a privileged threat and can read mounted server secrets/database."
