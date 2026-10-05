# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Layout

- `app/` Flask + WebAuthn server (`server.py`) and AES-256-GCM helpers (`privacy.py`)
- `java-biff-planner/` Maven Java planner
- `docs/` documentation (`docs/study/` study notes, `docs/biff-2026/` trip data)
- `scripts/` setup, key, and verification scripts
- `tests/` Python unit tests

## Commands

```bash
pip install -r requirements.txt
PYTHONPATH=app python -m unittest discover -s tests -v
```

## Private data API (`/api/private-values`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/private-values` | list (values masked) |
| POST | `/api/private-values` | create (`kind`, `label`, `value`) |
| PATCH | `/api/private-values/<id>` | update `label` and/or `value`; `kind` is immutable |
| DELETE | `/api/private-values/<id>` | delete |
| POST | `/api/private-values/<id>/reveal/*` | reveal, needs fresh WebAuthn assertion |

All routes require an authenticated WebAuthn session.

## Rules

- Never commit secrets, keys, or real personal data; secrets are file-based.
- Never log or return plaintext private values outside the reveal flow.
- Dependency updates arrive from Dependabot (`.github/dependabot.yml`, prefixes `deps(...)`); run the tests before merging them.
- Develop on the assigned branch and open a draft PR.
