#!/usr/bin/env bash
set -euo pipefail

RP_ID="${1:-localhost}"
ORIGIN="${2:-http://localhost:${HOST_PORT:-8080}}"

if [[ "${RP_ID}" != "localhost" && "${ORIGIN}" != https://* ]]; then
  echo "ERROR: Non-localhost WebAuthn origins must use HTTPS." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required to generate cryptographic secrets." >&2
  exit 1
fi

if [[ -e .env ]]; then
  echo "ERROR: .env already exists. Refusing to overwrite secrets." >&2
  exit 1
fi

umask 077
SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
BOOTSTRAP_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"

cat > .env <<EOF
SESSION_SECRET=${SESSION_SECRET}
WEBAUTHN_BOOTSTRAP_TOKEN=${BOOTSTRAP_TOKEN}
WEBAUTHN_RP_ID=${RP_ID}
WEBAUTHN_ORIGIN=${ORIGIN}
WEBAUTHN_RP_NAME=Codex Container Server
EOF

chmod 600 .env
echo "Created .env with mode 600."
echo "Do not commit or print the secrets in this file."
