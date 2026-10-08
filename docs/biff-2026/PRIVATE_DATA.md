# Private itinerary data

The public Git repository contains only non-sensitive itinerary details.

## What belongs in the encrypted vault

Use the authenticated web interface for values such as:

- SRT/KTX reservation numbers
- BIFF booking/order numbers
- hotel reservation numbers
- personal phone numbers
- personal email addresses
- other contact or booking references

Do **not** add those values to Markdown, Java source, GitHub Issues, pull requests, logs, container environment variables, or Docker image layers.

## Storage model

- Algorithm: AES-256-GCM
- Key: 256-bit URL-safe base64 value in `secrets/data_encryption_key`
- Persistent data: SQLite `private_values` table
- Stored columns: random record ID, kind, 96-bit nonce, ciphertext/authentication tag, timestamps
- Encrypted payload: label + original value
- Default display: masked only
- Full reveal: fresh FIDO2/WebAuthn assertion required
- Browser auto re-mask: 15 seconds

## Masking examples

- Reservation: `********1234`
- Phone: `***-****-5678`
- Email: `k***@e***.com`

These examples are synthetic and are not real user data.

## Existing deployment

```bash
./scripts/generate-data-encryption-key.sh
docker compose up -d --build
```

Keep the encryption key backup separate from the database backup.
