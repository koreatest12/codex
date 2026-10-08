#!/usr/bin/env bash
# CI-only integration smoke test for opt-in account + FIDO2 container mode.
# Never logs generated credentials and never runs against a production volume.
set -euo pipefail

IMAGE="${SERVER_IMAGE:-codex-linux-server:ci}"
APP_NAME="codex-admin-account-ci"
VOLUME="codex-admin-account-ci-data"
TEST_PORT="18080"
RUN_DIR="$(mktemp -d)"
chmod 700 "$RUN_DIR"

cleanup() {
  docker rm -f "$APP_NAME" >/dev/null 2>&1 || true
  docker volume rm "$VOLUME" >/dev/null 2>&1 || true
  rm -rf "$RUN_DIR"
}
trap cleanup EXIT

for key in SESSION_SECRET_FILE WEBAUTHN_BOOTSTRAP_TOKEN_FILE DATA_ENCRYPTION_KEY_FILE; do
  value="${!key:-}"
  if [[ ! -s "$value" ]]; then
    echo "Missing CI-only canary file for $key" >&2
    exit 1
  fi
done

# Write temporary salted scrypt hash + one-time login request to protected files.
# The plaintext canary is NOT printed or included in docker environment args.
PYTHONPATH=app .ci-python/bin/python - "$RUN_DIR" <<'PY'
import json
import secrets
import sys
from pathlib import Path
from admin_auth import make_account

dest = Path(sys.argv[1])
password = secrets.token_urlsafe(32)
(dest / "admin_account").write_text(
    json.dumps(make_account("admin", password)), encoding="utf-8"
)
(dest / "login.json").write_text(
    json.dumps({"username": "admin", "password": password}), encoding="utf-8"
)
for name in ("admin_account", "login.json"):
    (dest / name).chmod(0o600)
PY

abspath() {
  local path="$1"
  local dir base
  dir="$(cd "$(dirname "$path")" && pwd -P)"
  base="$(basename "$path")"
  printf '%s/%s\n' "$dir" "$base"
}

docker volume create "$VOLUME" >/dev/null
docker run -d \
  --name "$APP_NAME" \
  -p "127.0.0.1:${TEST_PORT}:8080" \
  -v "$VOLUME:/data" \
  --mount "type=bind,src=$(abspath "$SESSION_SECRET_FILE"),dst=/run/secrets/session_secret,readonly" \
  --mount "type=bind,src=$(abspath "$WEBAUTHN_BOOTSTRAP_TOKEN_FILE"),dst=/run/secrets/webauthn_bootstrap_token,readonly" \
  --mount "type=bind,src=$(abspath "$DATA_ENCRYPTION_KEY_FILE"),dst=/run/secrets/data_encryption_key,readonly" \
  --mount "type=bind,src=$RUN_DIR/admin_account,dst=/run/secrets/admin_account,readonly" \
  -e SESSION_SECRET_FILE=/run/secrets/session_secret \
  -e WEBAUTHN_BOOTSTRAP_TOKEN_FILE=/run/secrets/webauthn_bootstrap_token \
  -e DATA_ENCRYPTION_KEY_FILE=/run/secrets/data_encryption_key \
  -e ADMIN_ACCOUNT_FILE=/run/secrets/admin_account \
  -e WEBAUTHN_RP_ID=localhost \
  -e WEBAUTHN_ORIGIN=http://localhost:18080 \
  "$IMAGE" >/dev/null

base="http://127.0.0.1:${TEST_PORT}"
ready=no
for i in {1..45}; do
  if curl -fsS --max-time 3 "$base/healthz" >/dev/null 2>&1; then
    ready=yes
    break
  fi
  sleep 1
done
if [[ "$ready" != "yes" ]]; then
  echo "Account-gated container did not become healthy" >&2
  docker logs "$APP_NAME" >&2 || true
  exit 1
fi

status="$(curl -fsS "$base/api/security/status")"
printf '%s' "$status" | grep -q '"password_required":true'

code="$(curl -sS -o /dev/null -w '%{http_code}' "$base/api/system/status")"
[[ "$code" == 403 ]] || { echo "Unauthenticated status returned $code" >&2; exit 1; }

code="$(curl -sS -o "$RUN_DIR/login-out.json" -w '%{http_code}' \
  -c "$RUN_DIR/cookies" \
  -X POST -H "Content-Type: application/json" \
  --data-binary @"$RUN_DIR/login.json" \
  "$base/api/security/account/login")"
[[ "$code" == 200 ]] || { echo "Account login returned $code" >&2; exit 1; }
grep -q '"next_step":"webauthn"' "$RUN_DIR/login-out.json"

code="$(curl -sS -o /dev/null -w '%{http_code}' \
  -b "$RUN_DIR/cookies" "$base/api/system/status")"
[[ "$code" == 403 ]] || { echo "Password-only status was not blocked ($code)" >&2; exit 1; }

code="$(curl -sS -o /dev/null -w '%{http_code}' \
  -b "$RUN_DIR/cookies" -X POST -H "Content-Type: application/json" -d '{}' \
  "$base/api/security/authenticate/options")"
[[ "$code" == 409 ]] || { echo "Expected no FIDO2 credential yet; got $code" >&2; exit 1; }

echo "ACCOUNT-MODE CONTAINER INTEGRATION: PASS"
echo "- Ephemeral local admin credential verified, but password-only protected access blocked."
echo "- Hardware security key still required before access to /api/system/status."
echo "- No secret values were written to GitHub logs or container environment."
