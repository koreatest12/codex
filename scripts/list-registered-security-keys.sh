#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-codex-linux-server}"

if ! docker inspect "${CONTAINER_NAME}" >/dev/null 2>&1; then
  echo "ERROR: container not found: ${CONTAINER_NAME}" >&2
  exit 1
fi

docker exec -i "${CONTAINER_NAME}" /opt/venv/bin/python - <<'PY'
import hashlib
import json
import sqlite3

db = sqlite3.connect("/data/webauthn.db")
db.row_factory = sqlite3.Row
rows = db.execute(
    """
    SELECT credential_id, public_key, sign_count, transports, created_at
    FROM credentials
    ORDER BY created_at
    """
).fetchall()

print(f"registered_security_keys={len(rows)}")
for index, row in enumerate(rows, start=1):
    try:
        transports = json.loads(row["transports"])
    except Exception:
        transports = []
    credential_fp = hashlib.sha256(bytes(row["credential_id"])).hexdigest()
    public_fp = hashlib.sha256(bytes(row["public_key"])).hexdigest()
    print(f"key[{index}].credential_id_sha256={credential_fp}")
    print(f"key[{index}].public_key_sha256={public_fp}")
    print(f"key[{index}].sign_count={int(row['sign_count'])}")
    print(f"key[{index}].transports={','.join(transports)}")
    print(f"key[{index}].created_at={row['created_at']}")

print("private_key_stored=false")
PY
