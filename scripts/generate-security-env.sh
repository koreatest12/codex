#!/usr/bin/env bash
set -euo pipefail

RP_ID="${1:-localhost}"
ORIGIN="${2:-http://localhost:${HOST_PORT:-8080}}"
SECRETS_DIR="${SECRETS_DIR:-secrets}"

if [[ "${RP_ID}" != "localhost" && "${ORIGIN}" != https://* ]]; then
  echo "ERROR: Non-localhost WebAuthn origins must use HTTPS." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required to generate cryptographic secrets." >&2
  exit 1
fi

if [[ -e .env || -e "${SECRETS_DIR}/session_secret" || -e "${SECRETS_DIR}/webauthn_bootstrap_token" || -e "${SECRETS_DIR}/data_encryption_key" ]]; then
  echo "ERROR: Existing security configuration found. Refusing to overwrite it." >&2
  exit 1
fi

umask 077
mkdir -p "${SECRETS_DIR}"
chmod 700 "${SECRETS_DIR}"

python3 -c 'import secrets; print(secrets.token_urlsafe(48))' > "${SECRETS_DIR}/session_secret"
python3 -c 'import secrets; print(secrets.token_urlsafe(48))' > "${SECRETS_DIR}/webauthn_bootstrap_token"
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"))' > "${SECRETS_DIR}/data_encryption_key"
chmod 600 "${SECRETS_DIR}/session_secret" "${SECRETS_DIR}/webauthn_bootstrap_token" "${SECRETS_DIR}/data_encryption_key"

cat > .env <<EOF
WEBAUTHN_RP_ID=${RP_ID}
WEBAUTHN_ORIGIN=${ORIGIN}
WEBAUTHN_RP_NAME=Codex Container Server
EOF
chmod 600 .env

echo "Created .env plus read-only container secret source files."
echo "Secret values were not printed."
echo "For first-key registration, read the bootstrap token locally from:"
echo "  ${SECRETS_DIR}/webauthn_bootstrap_token"
