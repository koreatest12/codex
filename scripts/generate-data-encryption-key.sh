#!/usr/bin/env bash
set -euo pipefail

SECRETS_DIR="${SECRETS_DIR:-secrets}"
TARGET="${SECRETS_DIR}/data_encryption_key"

if [[ -e "${TARGET}" ]]; then
  echo "ERROR: ${TARGET} already exists; refusing to overwrite it." >&2
  exit 1
fi

command -v python3 >/dev/null 2>&1 || {
  echo "ERROR: python3 is required." >&2
  exit 1
}

umask 077
mkdir -p "${SECRETS_DIR}"
chmod 700 "${SECRETS_DIR}"
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"))' > "${TARGET}"
chmod 600 "${TARGET}"

echo "Created ${TARGET} without printing the key."
echo "Back up this key separately from the database. Losing it makes encrypted private values unrecoverable."
