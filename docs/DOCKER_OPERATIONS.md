# Docker deployment, CI images and persistent storage

The repository runs a Flask/WebAuthn application behind Gunicorn and Nginx,
with Java 21, javac, Maven and the compiled BIFF planner. A sanitized source
snapshot is included in each built image at /opt/codex-source. This includes
source files, docs, tests, CI workflow definitions and the public BIFF seed.
Runtime services remain under /opt/app and /opt/java-biff-planner. The image
MUST NOT contain credentials, private databases, host backups or .env.

## 1. Install Docker Engine on an Ubuntu host you administer

Run these commands on the actual Ubuntu host, not in GitHub Actions:

    git clone https://github.com/koreatest12/codex.git
    cd codex
    sudo bash scripts/install-docker-ubuntu.sh
    sudo docker version
    sudo docker compose version

The installer uses Docker's official apt repository and installs Docker
Engine, Buildx and Compose. It requires administrative privileges and
does not create a cloud VM, physical disk or public Docker TCP endpoint.
Review host installation scripts before running. Windows users should
use Docker Desktop with WSL2 rather than this Ubuntu-only installer.

## 2. Create/reuse a persistent logical disk (Docker volume)

    bash scripts/generate-security-env.sh localhost http://localhost:8080
    sudo bash scripts/prepare-docker-storage.sh
    sudo docker compose config --format json

By default the script detects the effective Docker Compose volume name
(such as codex_security-data when the Compose project is codex) and mounts
it at /data. It reuses existing project-scoped volumes to preserve saved
credentials and SQLite data. When using the separate manual Docker run
script, use bash scripts/prepare-docker-storage.sh --manual; that method
retains its original codex-security-data default. Run that mode with sudo
on root-controlled Ubuntu Docker Engine hosts.

A Docker named volume is NOT an allocated physical disk, a newly formatted
partition, or a reserved storage capacity. Provision/encrypt your own block
storage at the host/cloud level when needed.

IMPORTANT: Never run docker compose down -v or docker volume rm if you need
the saved WebAuthn credential records and encrypted private-value vault.

## 3. Generate secrets once, then build and start the server

    sudo bash scripts/build-image.sh
    sudo docker compose up -d --no-build
    sudo docker compose ps
    curl -fsS http://127.0.0.1:8080/healthz

Generation refuses to overwrite existing secrets or .env. To set up a real
domain, provide a matching HTTPS origin and terminate TLS with a secure
reverse proxy. The published app port is loopback-only by default. A FIDO2
hardware key must be registered interactively in the browser before
protected data access can work.

Check logs: sudo docker compose logs -f web

## 4. CI image builds and the registry

The file .github/workflows/docker-image-ci.yml runs for pull requests and
main-branch pushes. Docker Buildx checks that the sanitized repository
sources were packaged, that secret/local data paths are absent, that
Python unit tests pass, and that the Java CLI works.

On the main branch only, successful images are pushed to GitHub Container
Registry as:

- ghcr.io/koreatest12/codex:sha-<12-character-commit-sha>
- ghcr.io/koreatest12/codex:latest

The job uses GITHUB_TOKEN with packages:write. GitHub repository/package
permissions and package visibility can require adjustment. A successful
image CI build is NOT a successful deployment to a physical server.

To use a published image after it exists, set SERVER_IMAGE in your
local .env to an existing pinned SHA image tag and run:

    sudo docker compose pull web
    sudo docker compose up -d --no-build

This preserves the named /data volume. If the GHCR package is private,
authenticate with docker login ghcr.io using an appropriate access token.

The existing latest-linux-image.yml workflow additionally checks a
temporary running server, /healthz, WebAuthn gates, and defense tests.

## 5. Backups and disaster recovery

To avoid SQLite inconsistencies, stop writes before file-based backup. On
your own host, use a locked-down backup directory:

    mkdir -p backups
    chmod 700 backups
    sudo docker compose stop web
    volume=$(sudo docker compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["volumes"]["security-data"]["name"])')
    sudo docker run --rm -v "$volume:/data:ro" \
      -v "$PWD/backups:/backup" ubuntu:latest \
      sh -c 'tar -czf /backup/codex-data-backup.tar.gz -C /data .'
    sudo docker compose start web
    chmod 600 backups/codex-data-backup.tar.gz

Keep the backup confidential and encrypt/offload it separately. Store a
recoverable copy of secrets/data_encryption_key separately from the data
backup, in a secure location; encrypted fields cannot be decrypted without
the original key. Do not upload archives or keys to Git or a public registry.

## Security notes

Docker daemon permissions grant effective root-like host access; do not
expose the daemon socket to untrusted users. Docker image artifacts retain
a sanitized copy of tracked project content, not arbitrary host files.
New cloud server instances, real physical disks, public DNS, TLS, firewalls
and deployment credentials require separate host/cloud infrastructure.

## Administrator account and password + FIDO2 (opt-in)

For a **new installation**, first run the existing security environment
bootstrap to create encrypted-data keys and the local-only secrets directory:

    bash scripts/generate-security-env.sh localhost http://localhost:8080

For an **existing installation**, preserve the current .env, encryption key,
FIDO2 credential database and Docker volume: do NOT rerun the bootstrap.

In your own interactive Ubuntu/WSL terminal create the first admin account:

    python3 scripts/setup-admin-account.py --username admin

The script prints a unique randomly generated password to the **terminal once**.
Save that password in a password manager. Only a salted scrypt hash (not the
plaintext password) is stored under secrets/admin_account with permissions
0600. The secrets directory is excluded from Git/image builds.

Activate the password requirement explicitly with the Compose overlay:

    sudo docker compose -f compose.yaml -f compose.account.yaml up -d --build
    sudo docker compose -f compose.yaml -f compose.account.yaml ps

Access the configured origin, sign in as admin with the locally generated
password, **then** register/authenticate a physical FIDO2 hardware key.
An account password alone never grants access to the vault or data management.
For first-key registration, the original bootstrap token is still required.

To rotate an account credential (take a secure backup and plan downtime):

    python3 scripts/setup-admin-account.py --username admin --rotate
    sudo docker compose -f compose.yaml -f compose.account.yaml up -d --force-recreate

Rotating the credential file alone does not invalidate existing Flask session
cookies. Rotate session_secret as part of a planned maintenance window to
invalidate sessions (and securely preserve a copy of secrets first).

Previous FIDO2-only deployments are NOT automatically switched into account
mode: without the overlay, the original WebAuthn workflow stays supported.

This is a single local administrative account, not Linux useradd, SSH login,
Docker Hub/GitHub account creation, or a multi-tenant identity provider.
Administrator account provisioning happens on the chosen host, not in CI.

### Runtime status

After completing account + hardware-key login, the main web UI displays
"서버 최종 운영 상태" and reads GET /api/system/status. The route returns:
- current process uptime, configured authentication mode and admin username;
- registered FIDO2 keys, encrypted vault record count and AES-GCM state;
- local persistent database presence and filesystem total/free/used bytes.

This is runtime telemetry obtained **inside the app container**. It does not
prove external access, physical disk provisioning, registry publishing, or
cloud VM installation. The public /healthz endpoint deliberately reveals only
a minimum health signal. Unauthenticated /api/system/status returns HTTP 403.

For a credential-safe CLI check of the local Docker host:

    sudo bash scripts/final-status.sh

It shows actual Compose containers, images, persistent volume name and HTTP
health without printing password hashes or mounted secrets. This script
uses the account overlay automatically only when a local account file exists.
