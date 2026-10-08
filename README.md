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

Then create a new server without replacing any existing container. Export the
values matching your configuration (the following is the localhost example).
The generated `.env` is a Compose dotenv file, not a shell script; do not source it:

```bash
export WEBAUTHN_RP_ID=localhost
export WEBAUTHN_ORIGIN=http://localhost:8080
export WEBAUTHN_RP_NAME="Codex Container Server"
bash scripts/deploy-container-server.sh
```

If the default container name already exists, the script exits safely. See [Script deployment](#script-deployment) for a separate test deployment.

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

Compose has a different lifecycle from the preservation-first deployment script.
`docker compose up -d --build` can recreate an existing Compose-managed container.
Do not use it to test these changes or update a live deployment when containers must
be preserved. The commands below are for an explicitly intended Compose deployment.

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

Avoid `docker compose down` when preserving containers: it removes the project's containers.
The named `security-data` volume persists registered credential public keys and encrypted vault data when the container is recreated. Never remove its volume to perform an update.

For a separate Compose deployment, use a unique project name, container name, image
tag, and unused host port. Changing only the project name is insufficient because
this file declares `container_name` explicitly. A fresh project gets its own
`security-data` volume by default; do not override it to share an active server's
volume. Set `WEBAUTHN_ORIGIN` to match the separate deployment's exact browser URL.

## Script deployment

If you prefer the deployment script, load only the non-secret WebAuthn configuration and use the generated secret files:

```bash
export WEBAUTHN_RP_ID=localhost
export WEBAUTHN_ORIGIN=http://localhost:8080
export WEBAUTHN_RP_NAME="Codex Container Server"
chmod +x scripts/deploy-container-server.sh
./scripts/deploy-container-server.sh
```

The deployment script mounts `secrets/session_secret`, `secrets/webauthn_bootstrap_token`, and `secrets/data_encryption_key` read-only instead of putting their values in Docker environment variables.

### Container and data preservation

The script never deletes, stops, restarts, or replaces an existing container.
An existing `CONTAINER_NAME`, even when stopped, causes an early exit before pulling
or building. Failure to list containers also stops deployment. A competing attempt
to claim the same name fails safely at creation. The new container uses the immutable
image ID produced by this build, and subsequent checks use its captured container ID.

Created containers and data volumes remain after success or failure, including a
port conflict or failed readiness check. The legacy `CLEANUP_AFTER_TEST` setting is
ignored with a warning. There is no implicit cleanup or replacement. Readiness
checks have bounded retries and per-request timeouts, so an unresponsive service
fails verification instead of waiting indefinitely.

To test alongside an existing server, choose a fresh container name, image tag,
data volume, and unused host port. For example, after checking those are free and
loading your non-secret configuration as above:

```bash
CONTAINER_NAME=codex-linux-server-check-1 \
SERVER_IMAGE=codex-linux-server:check-1 \
DATA_VOLUME=codex-security-data-check-1 \
HOST_PORT=9090 \
WEBAUTHN_ORIGIN=http://localhost:9090 \
bash scripts/deploy-container-server.sh
```

This localhost example assumes `WEBAUTHN_RP_ID=localhost`. Use matching HTTPS origin
and RP settings for a real domain. Do not reuse that name or volume for another
parallel test. Reusing an active server's data volume lets both servers write the
same databases and can change existing credentials or encrypted vault data.
A fresh volume starts empty and does not migrate the existing deployment.

Inspect retained containers without changing them:

```bash
docker ps -a --filter 'name=^/codex-linux-server$'
docker container inspect --format 'ID={{.Id}} Status={{.State.Status}}' codex-linux-server
```

The base-image smoke test also retains its container after it exits. Retention uses
disk space; removal is a separate, explicit operator decision. These changes do not
perform a live deployment or authorize replacing an existing server.

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
6. Confirms `/healthz`, including the published host port with bounded curl timeouts.
7. Confirms from the host that the unauthenticated page requires a security key.
8. Confirms from the host that the WebAuthn status API is enabled.
9. Confirms security response headers from the host.
10. Runs a disposable canary-based attack simulation for secret leakage and unauthorized registration.
11. Verifies that the WebAuthn database has no hardware private-key field.
12. Verifies the Java toolchain inside the retained server container.
13. Confirms the actual server image was built successfully.

Python privacy, versioned-data, and mock-Docker preservation tests run before the
live container checks. Workflow runs use distinct image tags, container names, and
data volume names based on the GitHub run ID and attempt. No step removes
containers or data volumes. Canary secret files alone are cleaned up at the end;
CI containers are retained only for the lifetime of the GitHub-hosted runner and
are not persistent storage after runner teardown.

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
```

This only prepares the key file. Applying it to an existing server requires an
explicitly planned deployment; Compose may recreate the container. Do not run a
live update merely to test these preservation changes.

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


## Container safety regression tests

Run only the mock-Docker preservation tests without Docker or network access:

```bash
python3 -m unittest discover -s tests -p 'test_container*.py' -v
for script in scripts/deploy-container-server.sh scripts/run-latest-linux.sh; do
  bash -n "$script" || exit 1
done
```

These tests exercise name conflicts, ID targeting, bounded checks, and retention
without creating or removing real containers. The full test suite also requires
the Python dependencies listed in `requirements.txt`.
