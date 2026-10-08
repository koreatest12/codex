# Security

## FIDO2 / WebAuthn security-key authentication

The container server requires WebAuthn authentication for protected access.

Security properties:

- No password fallback is implemented.
- User verification is required during registration and authentication.
- Registration requests prefer cross-platform authenticators such as FIDO2 hardware security keys.
- The first key can only be registered with the bootstrap token.
- Once at least one key exists, the bootstrap token alone can no longer register another key.
- Additional backup keys require an already authenticated session.
- Challenges are single-use and bound to the signed server session.
- Credential public keys and signature counters are stored in SQLite under `/data`.
- Session cookies are HttpOnly and SameSite=Strict; Secure is enabled automatically for HTTPS origins.
- Non-localhost WebAuthn origins are rejected unless they use HTTPS.
- Security headers block framing and restrict WebAuthn browser permissions to the same origin.

## Initial setup

Generate strong secrets locally. Never commit them.

For localhost testing:

```bash
./scripts/generate-security-env.sh localhost http://localhost:8080
docker compose up -d --build
```

For a real domain:

```bash
./scripts/generate-security-env.sh server.example.com https://server.example.com
docker compose up -d --build
```

Place an HTTPS reverse proxy/load balancer in front of the localhost-bound container for remote access.

Open the configured origin, enter the bootstrap token from `.env`, and register the first hardware security key.

After first registration, keep at least one second FIDO2 key as a recovery key. Add it only while authenticated with the first key.

## Important operational controls

- Secret values are stored in local files under `secrets/`, not in container environment variables. Keep that directory mode-restricted and readable only by the server administrator.
- Back up the persistent Docker volume that contains `/data/webauthn.db`.
- Restrict Docker socket access; anyone with Docker daemon control can bypass application-level controls.
- Restrict SSH and server administration separately with MFA/security keys.
- Use a firewall and expose only the HTTPS reverse proxy.
- Rotate `secrets/session_secret` after suspected compromise; this invalidates existing sessions.
- Rotate `secrets/webauthn_bootstrap_token` after initial setup even though bootstrap registration is disabled once a key exists.
- Losing every registered security key and the credential database can cause administrative lockout.

GitHub account security-key/2FA configuration is account-level and is separate from this repository's server authentication.


## What is stored after security-key registration

The hardware authenticator private key is never uploaded to this repository or container. The server stores only the WebAuthn credential ID, credential public key, signature counter, transport metadata, and creation time in `/data/webauthn.db`.

To review registered keys without printing raw credential/public-key material:

```bash
./scripts/list-registered-security-keys.sh
```

The command prints SHA-256 fingerprints only and ends with `private_key_stored=false`.

## Defensive attack simulation

`scripts/security-attack-simulation.sh` performs an authorized, non-destructive simulation against this container. CI uses disposable canary secrets and checks that:

- secret values do not appear in `docker inspect` environment output;
- secret values do not appear in the application process environment;
- public HTTP routes and attempted sensitive-file paths do not expose the canaries;
- missing or incorrect bootstrap tokens receive HTTP 403;
- unauthenticated credential enumeration receives HTTP 403;
- application logs do not contain the canaries;
- the WebAuthn database schema contains a public-key column but no private-key/secret-key column.

This does not claim protection from host-root or Docker-daemon compromise. A process with root/Docker control can read mounted server secret files and the WebAuthn database. Even in that scenario, a correctly functioning FIDO2 hardware authenticator's private key is not present on the server and is therefore not available to exfiltrate from the container.


## Encrypted private-data vault

Reservation numbers, phone numbers, email addresses, and other private itinerary values must not be committed to Git.

The authenticated web UI provides a private-data vault with these controls:

- AES-256-GCM authenticated encryption at rest.
- A dedicated 256-bit data-encryption key stored only in a Docker/file secret.
- SQLite stores only `record_id`, `kind`, a 96-bit nonce, ciphertext/tag, and timestamps.
- Labels and original values are both inside the encrypted payload.
- List responses show masked values only.
- Revealing the original value requires a fresh WebAuthn assertion even when a session is already authenticated.
- Revealed values are automatically re-masked in the browser after 15 seconds.
- Nginx rate-limits the private-data API.
- The defensive attack simulation checks that the data-encryption key is absent from HTTP responses, process/container environment output, and logs.

### Existing installation upgrade

```bash
chmod +x scripts/generate-data-encryption-key.sh
./scripts/generate-data-encryption-key.sh
docker compose up -d --build
```

Back up `secrets/data_encryption_key` separately from the SQLite volume. If that key is lost, encrypted private values cannot be recovered.

For planned key rotation, use `scripts/rotate-data-encryption-key.py` while the application is stopped and after making a database backup.

Never commit the key, reservation numbers, phone numbers, or other raw private values.
