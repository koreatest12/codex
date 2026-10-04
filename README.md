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

Generate a local `.env` file. Real secrets are intentionally never stored in Git.

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

Open the exact URL configured in `WEBAUTHN_ORIGIN`. For the first registration only, enter the `WEBAUTHN_BOOTSTRAP_TOKEN` from the server's `.env` file and register your hardware security key.

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

If you prefer the deployment script, export the required variables first:

```bash
set -a
source .env
set +a
chmod +x scripts/deploy-container-server.sh
./scripts/deploy-container-server.sh
```

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
10. Confirms the final image was built successfully.

CI cannot physically press a hardware key, so cryptographic registration/login must be completed interactively in a browser after deployment.

See [SECURITY.md](SECURITY.md) for deployment and recovery requirements.
