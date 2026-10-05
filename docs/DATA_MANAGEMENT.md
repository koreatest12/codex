# Data management

This repository now separates two data classes:

1. **Public operational data** — itinerary, venue, timing, restaurant metadata, study notes. Managed by the versioned data manager.
2. **Private data** — reservation/order numbers, phone numbers, email addresses, contact details. Stored only in the encrypted private-data vault.

## Dependabot

`.github/dependabot.yml` monitors:

- Python/pip dependencies at repository root
- Maven dependencies under `java-biff-planner/`
- Docker base images at repository root
- GitHub Actions

The schedule is weekly on Monday morning in `Asia/Seoul`. Minor/patch updates are grouped to reduce PR noise; major updates remain separate for review.

GitHub's Dependency Review action requires the repository Dependency Graph to be enabled. It is intentionally not made a required workflow here because this repository currently reports Dependency Review as unsupported. Dependabot version updates remain active from the configuration file; enable Dependency Graph in repository security settings before adding Dependency Review as a blocking check.

## Versioned data manager

Storage: `/data/managed-data.db` by default.

Features:

- create/list datasets
- create/update/delete records
- optimistic revision checks with `expected_revision`
- SHA-256 integrity checksums
- immutable record history/audit snapshots
- JSON export/import
- full integrity verification
- atomic SQLite transactions
- rejection of likely reservation/contact fields from the public store
- `private_ref` / `private_refs` fields for linking to the encrypted vault without copying secrets

### CLI

```bash
codex-data-manager init
codex-data-manager create-dataset biff-2026 --description "public itinerary"
codex-data-manager put biff-2026 opening --json '{"date":"2026-10-06","time":"18:00"}'
codex-data-manager list biff-2026
codex-data-manager history biff-2026 opening
codex-data-manager verify
codex-data-manager export --output backup.json
```

Seed the checked-in public BIFF data:

```bash
codex-data-manager import /opt/biff-data/seed.json
codex-data-manager verify
```

For local repository use:

```bash
python3 scripts/data-manager.py --db /tmp/managed.db import data/biff-2026/seed.json
python3 scripts/data-manager.py --db /tmp/managed.db verify
```

## API

All `/api/data/*` endpoints require an authenticated WebAuthn session.

- `GET /api/data/datasets`
- `POST /api/data/datasets`
- `GET /api/data/datasets/<dataset_id>`
- `GET /api/data/datasets/<dataset_id>/records`
- `POST /api/data/datasets/<dataset_id>/records`
- `GET /api/data/datasets/<dataset_id>/records/<record_id>`
- `PUT /api/data/datasets/<dataset_id>/records/<record_id>`
- `DELETE /api/data/datasets/<dataset_id>/records/<record_id>`
- `GET /api/data/datasets/<dataset_id>/records/<record_id>/history`
- `GET /api/data/export[?dataset=<id>]`
- `GET /api/data/verify[?dataset=<id>]`

## Sensitive-data guard

The public data manager rejects keys such as `reservation`, `booking`, `phone`, `email`, and similar contact/confirmation fields. It also rejects obvious email addresses and Korean mobile-phone patterns found in string values.

Store those values in the encrypted private-data vault and keep only a non-secret `private_ref` in public data.
