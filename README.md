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
