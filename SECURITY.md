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

- Keep `.env` readable only by the server administrator.
- Back up the persistent Docker volume that contains `/data/webauthn.db`.
- Restrict Docker socket access; anyone with Docker daemon control can bypass application-level controls.
- Restrict SSH and server administration separately with MFA/security keys.
- Use a firewall and expose only the HTTPS reverse proxy.
- Rotate `SESSION_SECRET` after suspected compromise; this invalidates existing sessions.
- Rotate `WEBAUTHN_BOOTSTRAP_TOKEN` after initial setup even though bootstrap registration is disabled once a key exists.
- Losing every registered security key and the credential database can cause administrative lockout.

GitHub account security-key/2FA configuration is account-level and is separate from this repository's server authentication.
