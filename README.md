# codex

Ubuntu container server with FIDO2/WebAuthn hardware security-key authentication.

## Security model

The web server is protected by WebAuthn rather than a password fallback.

- FIDO2/WebAuthn security-key authentication is required for protected access.
- User verification is required for registration and login.
- The first key requires a high-entropy bootstrap token.
- After the first key is registered, the bootstrap token alone cannot add more keys.
- Additional backup keys require an authenticated WebAuthn session.
- Credential public keys and signature counters are stored in a persistent SQLite database.
- Non-localhost WebAuthn origins must use HTTPS.
- Sessions use HttpOnly and SameSite=Strict cookies; HTTPS sessions also use Secure cookies.
- Nginx rate-limits authentication API calls.
- The container binds to localhost by default, reducing accidental public exposure.

The WebAuthn server uses `webauthn==3.0.1`, Flask `3.1.3`, and Gunicorn `26.2.0`.

## Initial security-key setup

Generate local configuration plus file-based secrets. Real secret values are intentionally never stored in Git or container environment variables.

Localhost:

```bash
chmod +x scripts/generate-security-env.sh
./scripts/generate-security-env.sh localhost http://localhost:8080
```

Real domain:

```bash
./scripts/generate-security-env.sh server.example.com https://server.example.com
```

For a non-localhost domain, terminate TLS with an HTTPS reverse proxy/load balancer and keep this container bound to localhost.

Then start the server:

```bash
docker compose up -d --build
```

Open the exact URL configured in `WEBAUTHN_ORIGIN`. For the first registration only, read the token locally from `secrets/webauthn_bootstrap_token`, enter it in the registration page, and register your hardware security key. The hardware private key remains inside the authenticator; only credential/public-key data is stored in the server database.

After login, use **백업 보안키 추가** to register a second hardware key. Keeping two separate keys is strongly recommended to avoid lockout.

## Architecture

1. Pull the official `ubuntu:latest` base image.
2. Build an Ubuntu image with Nginx, Gunicorn, Flask, and WebAuthn verification.
3. Nginx listens on container port 8080.
4. Gunicorn serves the WebAuthn application internally on 127.0.0.1:8000.
5. WebAuthn credentials are persisted under `/data/webauthn.db`.
6. Docker health checks verify the complete Nginx-to-application path.
7. GitHub Actions verifies the security gate, status endpoint, and response security headers.

## Docker Compose

Start:

```bash
docker compose up -d --build
```

Status:

```bash
docker compose ps
```

Logs:

```bash
docker compose logs -f
```

Stop:

```bash
docker compose down
```

The named `security-data` volume persists registered credential public keys when the container is recreated.

## Script deployment

If you prefer the deployment script, load only the non-secret WebAuthn configuration and use the generated secret files:

```bash
set -a
source .env
set +a
chmod +x scripts/deploy-container-server.sh
./scripts/deploy-container-server.sh
```

The deployment script mounts `secrets/session_secret` and `secrets/webauthn_bootstrap_token` read-only instead of putting their values in Docker environment variables.

Default local URL:

```text
http://127.0.0.1:8080
```

Health endpoint:

```bash
curl http://127.0.0.1:8080/healthz
```

Security status endpoint:

```bash
curl http://127.0.0.1:8080/api/security/status
```

## GitHub Actions

The workflow automatically:

1. Pulls `ubuntu:latest`.
2. Runs the base Linux smoke test.
3. Builds the WebAuthn-protected server image.
4. Creates an ephemeral CI secret and bootstrap token at runtime.
5. Starts the server container.
6. Confirms `/healthz`.
7. Confirms that the unauthenticated page requires a security key.
8. Confirms the WebAuthn status API is enabled.
9. Confirms security response headers.
10. Runs a disposable canary-based attack simulation for secret leakage and unauthorized registration.
11. Verifies that the WebAuthn database has no hardware private-key field.
12. Confirms the final image was built successfully.

CI cannot physically press a hardware key, so cryptographic registration/login must be completed interactively in a browser after deployment.

See [SECURITY.md](SECURITY.md) for deployment and recovery requirements.


## Registered security-key inventory

After you physically register a FIDO2 key in the browser, verify that the container recorded only server-side public metadata:

```bash
chmod +x scripts/list-registered-security-keys.sh
./scripts/list-registered-security-keys.sh
```

It prints SHA-256 fingerprints rather than raw credential/public-key bytes and reports `private_key_stored=false`.

For a safe defensive leak test against your own container:

```bash
chmod +x scripts/security-attack-simulation.sh
./scripts/security-attack-simulation.sh
```

The simulation uses the configured canary/server secrets only for comparison and does not print them. It verifies that common unauthenticated HTTP requests, logs, process environment output, and Docker environment metadata do not disclose those values.


## BIFF 2026 itinerary and Java/Maven toolchain

This repository also contains the consolidated 2026 Busan International Film Festival itinerary:

- [Final itinerary](docs/biff-2026/ITINERARY.md)
- [Food and coffee guide](docs/biff-2026/FOOD_AND_COFFEE.md)
- [Official/source checklist](docs/biff-2026/SOURCES.md)

A Java 21 command-line planner is available under `java-biff-planner/`.

Build and run:

```bash
chmod +x scripts/verify-java-toolchain.sh
./scripts/verify-java-toolchain.sh

java -jar java-biff-planner/target/biff-planner-1.0.0.jar all
```

The Docker image now installs:

- OpenJDK 21 JDK
- `java`
- `javac`
- Maven
- the precompiled BIFF planner JAR under `/opt/java-biff-planner/target/`

GitHub Actions verifies Java 21, the compiler, Maven, the Maven package build, the CLI smoke test, and the same toolchain again inside the final Ubuntu container.

The itinerary intentionally omits reservation IDs, personal contact information, and other secrets even though the repository is public.

## Encrypted reservation/contact vault

Authenticated users can store reservation numbers and personal contact values in the web UI without committing them to Git.

- AES-256-GCM encryption at rest.
- Dedicated key mounted from `secrets/data_encryption_key`.
- Labels and values are encrypted together.
- Lists return masked values only.
- Raw reveal requires a fresh FIDO2/WebAuthn assertion and is re-masked in the browser after 15 seconds.
- Nginx rate-limits the private-data API.
- The Java planner includes a stdin-only masking helper.

New installs get the encryption key from `scripts/generate-security-env.sh`.

Existing installs must create it once:

```bash
chmod +x scripts/generate-data-encryption-key.sh
./scripts/generate-data-encryption-key.sh
docker compose up -d --build
```

See [docs/biff-2026/PRIVATE_DATA.md](docs/biff-2026/PRIVATE_DATA.md) and [SECURITY.md](SECURITY.md).

## Study notes

정보보안기사·개발 준비용 디지털시스템 정리: [docs/study/DIGITAL_SYSTEMS.md](docs/study/DIGITAL_SYSTEMS.md)


## Dependabot and versioned data management

Dependency update automation is configured in [.github/dependabot.yml](.github/dependabot.yml) for pip, Maven, Docker, and GitHub Actions. Minor/patch updates are grouped; major updates remain individually reviewable.

Public BIFF/application data can be created and maintained through the versioned data manager:

```bash
python3 scripts/data-manager.py --db /tmp/managed.db import data/biff-2026/seed.json
python3 scripts/data-manager.py --db /tmp/managed.db verify
python3 scripts/data-manager.py --db /tmp/managed.db export --output backup.json
```

Inside the container the command is installed as `codex-data-manager`, using `/data/managed-data.db` by default.

The manager provides revisions, SHA-256 integrity checks, history, optimistic update checks, import/export, and a sensitive-data guard. Reservation/contact values continue to belong only in the encrypted private-data vault.

See [docs/DATA_MANAGEMENT.md](docs/DATA_MANAGEMENT.md).


## Docker image CI, full source snapshot and persistent storage

Every built Ubuntu image now packages a **sanitized copy of the repository**
under /opt/codex-source, including source, documentation, tests, workflow
definitions and the public data seed. Local environment files, private
data, security keys, databases and backups are excluded by .dockerignore.

On an Ubuntu Server host, scripts/install-docker-ubuntu.sh can install
Docker Engine, Buildx and Compose (with sudo). Run
scripts/prepare-docker-storage.sh to detect and reuse the existing
Compose project-specific persistent data volume, then scripts/build-image.sh to build
and test the local image.

The separate Docker Image CI workflow checks pull-request images and
publishes successful main-branch images to GitHub Container Registry
as latest and immutable commit-SHA tags. This creates image artifacts,
but does not provision or deploy a remote cloud server.

See [Docker operations and backups](docs/DOCKER_OPERATIONS.md)
for commands, data preservation, image upgrades and security limits.


## Optional administrator username, password and final runtime status

To set up a local single-administrator account without weakening hardware-key
requirements, first generate the existing .env and local secret files if
this is a new deployment. Then run:

    python3 scripts/setup-admin-account.py --username admin
    sudo docker compose -f compose.yaml -f compose.account.yaml up -d --build

The password is randomly generated locally, shown once in an interactive
terminal, and **never committed to Git**. Only a salted scrypt hash is
mounted to the container as a read-only secret. After entering credentials,
users must still complete a FIDO2/WebAuthn challenge. Existing FIDO2-only
deployments are left unchanged unless the Compose account overlay is enabled.

After login, the protected "서버 최종 운영 상태" UI shows authentication
mode, key registrations, vault count, container uptime and filesystem
capacity. For a host-side summary without printing secrets:

    sudo bash scripts/final-status.sh

See [administrator access and runtime status](docs/DOCKER_OPERATIONS.md).


## CI secret-source conflict regression hardening

The Flask server intentionally rejects configurations containing both
`SESSION_SECRET` and `SESSION_SECRET_FILE` (likewise for WebAuthn
bootstrap and encryption keys). No insecure password/secret fallback is
added. The tests isolate their environment from inherited Actions runner
variables, while subprocess integration tests cover file-only, direct-only,
missing and conflicting secret configuration. The Linux container workflow
also runs a redacted file-mode preflight.

See [duplicate-secret troubleshooting](docs/DOCKER_OPERATIONS.md).
