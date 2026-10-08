#!/usr/bin/env bash
set -euo pipefail

SESSION_SECRET_SOURCE_FILE="${SESSION_SECRET_SOURCE_FILE:-/run/secrets/session_secret}"
WEBAUTHN_BOOTSTRAP_TOKEN_SOURCE_FILE="${WEBAUTHN_BOOTSTRAP_TOKEN_SOURCE_FILE:-/run/secrets/webauthn_bootstrap_token}"
DATA_ENCRYPTION_KEY_SOURCE_FILE="${DATA_ENCRYPTION_KEY_SOURCE_FILE:-/run/secrets/data_encryption_key}"
INTERNAL_SECRET_DIR="/run/codex-secrets"

install -d -m 0700 -o www-data -g www-data "${INTERNAL_SECRET_DIR}"

for source in "${SESSION_SECRET_SOURCE_FILE}" "${WEBAUTHN_BOOTSTRAP_TOKEN_SOURCE_FILE}" "${DATA_ENCRYPTION_KEY_SOURCE_FILE}"; do
  if [[ ! -f "${source}" || ! -s "${source}" ]]; then
    echo "ERROR: required secret source is missing or empty: ${source}" >&2
    exit 1
  fi
done

install -m 0400 -o www-data -g www-data "${SESSION_SECRET_SOURCE_FILE}" "${INTERNAL_SECRET_DIR}/session_secret"
install -m 0400 -o www-data -g www-data "${WEBAUTHN_BOOTSTRAP_TOKEN_SOURCE_FILE}" "${INTERNAL_SECRET_DIR}/webauthn_bootstrap_token"
install -m 0400 -o www-data -g www-data "${DATA_ENCRYPTION_KEY_SOURCE_FILE}" "${INTERNAL_SECRET_DIR}/data_encryption_key"

export SESSION_SECRET_FILE="${INTERNAL_SECRET_DIR}/session_secret"
export WEBAUTHN_BOOTSTRAP_TOKEN_FILE="${INTERNAL_SECRET_DIR}/webauthn_bootstrap_token"
export DATA_ENCRYPTION_KEY_FILE="${INTERNAL_SECRET_DIR}/data_encryption_key"

exec supervisord -c /etc/supervisor/conf.d/codex.conf
