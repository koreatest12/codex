import hashlib
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SENSITIVE_KEY_RE = re.compile(
    r"(reservation|booking|confirmation|pnr|phone|mobile|telephone|email|contact|"
    r"ticket[_-]?number|account[_-]?number)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_KR_PHONE_RE = re.compile(r"(?<!\d)01[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
_MAX_PAYLOAD_BYTES = 64 * 1024


class DataManagerError(Exception):
    pass


class NotFound(DataManagerError):
    pass


class RevisionConflict(DataManagerError):
    pass


class SensitiveDataError(DataManagerError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _validate_id(value: str, field: str) -> str:
    normalized = (value or "").strip()
    if not _ID_RE.fullmatch(normalized):
        raise DataManagerError(
            f"{field} must match {_ID_RE.pattern} and be at most 64 characters"
        )
    return normalized


def _validate_payload(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise DataManagerError(f"{path}: object keys must be strings")
            if key not in {"private_ref", "private_refs"} and _SENSITIVE_KEY_RE.search(key):
                raise SensitiveDataError(
                    f"{path}.{key}: private fields belong in the encrypted private-data vault"
                )
            _validate_payload(child, f"{path}.{key}")
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_payload(child, f"{path}[{index}]")
        return

    if value is None or isinstance(value, (bool, int)):
        return

    if isinstance(value, float):
        if not math.isfinite(value):
            raise DataManagerError(f"{path}: NaN/Infinity are not supported")
        return

    if isinstance(value, str):
        if _EMAIL_RE.fullmatch(value.strip()) or _KR_PHONE_RE.search(value):
            raise SensitiveDataError(
                f"{path}: detected contact data; store it in the encrypted private-data vault"
            )
        return

    raise DataManagerError(f"{path}: unsupported JSON value type {type(value).__name__}")


def _canonical_json(payload: Any) -> str:
    _validate_payload(payload)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if len(encoded.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise DataManagerError("record payload exceeds 64 KiB")
    return encoded


def _checksum(canonical_json: str) -> str:
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class DataManager:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS managed_datasets (
                    dataset_id TEXT PRIMARY KEY,
                    description TEXT NOT NULL DEFAULT '',
                    revision INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS managed_records (
                    dataset_id TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(dataset_id, record_id),
                    FOREIGN KEY(dataset_id)
                      REFERENCES managed_datasets(dataset_id)
                      ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS managed_history (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dataset_id TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    record_revision INTEGER NOT NULL,
                    operation TEXT NOT NULL,
                    payload TEXT,
                    checksum TEXT,
                    changed_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_managed_history_record
                ON managed_history(dataset_id, record_id, history_id);
                """
            )

    def create_dataset(self, dataset_id: str, description: str = "") -> dict[str, Any]:
        dataset_id = _validate_id(dataset_id, "dataset_id")
        description = (description or "").strip()
        if len(description) > 500:
            raise DataManagerError("description must be at most 500 characters")
        _validate_payload({"description": description})
        now = _utc_now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO managed_datasets(dataset_id, description, revision, created_at, updated_at)
                    VALUES (?, ?, 0, ?, ?)
                    """,
                    (dataset_id, description, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise RevisionConflict(f"dataset already exists: {dataset_id}") from exc
        return self.get_dataset(dataset_id)

    def list_datasets(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT d.dataset_id, d.description, d.revision, d.created_at, d.updated_at,
                       COUNT(r.record_id) AS record_count
                FROM managed_datasets d
                LEFT JOIN managed_records r ON r.dataset_id = d.dataset_id
                GROUP BY d.dataset_id
                ORDER BY d.dataset_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        dataset_id = _validate_id(dataset_id, "dataset_id")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT d.dataset_id, d.description, d.revision, d.created_at, d.updated_at,
                       COUNT(r.record_id) AS record_count
                FROM managed_datasets d
                LEFT JOIN managed_records r ON r.dataset_id = d.dataset_id
                WHERE d.dataset_id = ?
                GROUP BY d.dataset_id
                """,
                (dataset_id,),
            ).fetchone()
        if row is None:
            raise NotFound(f"dataset not found: {dataset_id}")
        return dict(row)

    def list_records(self, dataset_id: str) -> list[dict[str, Any]]:
        self.get_dataset(dataset_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record_id, payload, checksum, revision, created_at, updated_at
                FROM managed_records
                WHERE dataset_id = ?
                ORDER BY record_id
                """,
                (dataset_id,),
            ).fetchall()
        return [self._record_dict(dataset_id, row) for row in rows]

    def get_record(self, dataset_id: str, record_id: str) -> dict[str, Any]:
        dataset_id = _validate_id(dataset_id, "dataset_id")
        record_id = _validate_id(record_id, "record_id")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT record_id, payload, checksum, revision, created_at, updated_at
                FROM managed_records
                WHERE dataset_id = ? AND record_id = ?
                """,
                (dataset_id, record_id),
            ).fetchone()
        if row is None:
            raise NotFound(f"record not found: {dataset_id}/{record_id}")
        return self._record_dict(dataset_id, row)

    def put_record(
        self,
        dataset_id: str,
        record_id: str,
        payload: dict[str, Any],
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        dataset_id = _validate_id(dataset_id, "dataset_id")
        record_id = _validate_id(record_id, "record_id")
        if not isinstance(payload, dict):
            raise DataManagerError("record payload must be a JSON object")
        canonical = _canonical_json(payload)
        digest = _checksum(canonical)
        now = _utc_now()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            dataset = connection.execute(
                "SELECT revision FROM managed_datasets WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
            if dataset is None:
                raise NotFound(f"dataset not found: {dataset_id}")

            current = connection.execute(
                """
                SELECT revision, created_at, checksum
                FROM managed_records
                WHERE dataset_id = ? AND record_id = ?
                """,
                (dataset_id, record_id),
            ).fetchone()

            current_revision = int(current["revision"]) if current else 0
            if expected_revision is not None and expected_revision != current_revision:
                raise RevisionConflict(
                    f"expected revision {expected_revision}, current revision {current_revision}"
                )

            if current is not None and current["checksum"] == digest:
                return self.get_record(dataset_id, record_id)

            new_revision = current_revision + 1
            created_at = current["created_at"] if current else now
            connection.execute(
                """
                INSERT INTO managed_records(
                    dataset_id, record_id, payload, checksum, revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id, record_id) DO UPDATE SET
                    payload = excluded.payload,
                    checksum = excluded.checksum,
                    revision = excluded.revision,
                    updated_at = excluded.updated_at
                """,
                (
                    dataset_id,
                    record_id,
                    canonical,
                    digest,
                    new_revision,
                    created_at,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO managed_history(
                    dataset_id, record_id, record_revision, operation,
                    payload, checksum, changed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_id,
                    record_id,
                    new_revision,
                    "create" if current is None else "update",
                    canonical,
                    digest,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE managed_datasets
                SET revision = revision + 1, updated_at = ?
                WHERE dataset_id = ?
                """,
                (now, dataset_id),
            )

        return self.get_record(dataset_id, record_id)

    def delete_record(
        self,
        dataset_id: str,
        record_id: str,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        current = self.get_record(dataset_id, record_id)
        if expected_revision is not None and expected_revision != current["revision"]:
            raise RevisionConflict(
                f"expected revision {expected_revision}, current revision {current['revision']}"
            )
        now = _utc_now()
        tombstone_revision = current["revision"] + 1
        canonical = _canonical_json(current["data"])
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO managed_history(
                    dataset_id, record_id, record_revision, operation,
                    payload, checksum, changed_at
                ) VALUES (?, ?, ?, 'delete', ?, ?, ?)
                """,
                (
                    dataset_id,
                    record_id,
                    tombstone_revision,
                    canonical,
                    current["checksum"],
                    now,
                ),
            )
            cursor = connection.execute(
                "DELETE FROM managed_records WHERE dataset_id = ? AND record_id = ?",
                (dataset_id, record_id),
            )
            if cursor.rowcount == 0:
                raise NotFound(f"record not found: {dataset_id}/{record_id}")
            connection.execute(
                """
                UPDATE managed_datasets
                SET revision = revision + 1, updated_at = ?
                WHERE dataset_id = ?
                """,
                (now, dataset_id),
            )
        return {"deleted": True, "dataset_id": dataset_id, "record_id": record_id}

    def history(self, dataset_id: str, record_id: str) -> list[dict[str, Any]]:
        dataset_id = _validate_id(dataset_id, "dataset_id")
        record_id = _validate_id(record_id, "record_id")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record_revision, operation, payload, checksum, changed_at
                FROM managed_history
                WHERE dataset_id = ? AND record_id = ?
                ORDER BY history_id
                """,
                (dataset_id, record_id),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["data"] = json.loads(item.pop("payload")) if item["payload"] else None
            result.append(item)
        return result

    def export_bundle(self, dataset_id: str | None = None) -> dict[str, Any]:
        datasets = [self.get_dataset(dataset_id)] if dataset_id else self.list_datasets()
        return {
            "schema_version": 1,
            "exported_at": _utc_now(),
            "datasets": [
                {
                    "id": item["dataset_id"],
                    "description": item["description"],
                    "revision": item["revision"],
                    "records": self.list_records(item["dataset_id"]),
                }
                for item in datasets
            ],
        }

    def import_bundle(self, bundle: dict[str, Any]) -> dict[str, int]:
        if not isinstance(bundle, dict) or bundle.get("schema_version") != 1:
            raise DataManagerError("unsupported import bundle")
        datasets = bundle.get("datasets")
        if not isinstance(datasets, list):
            raise DataManagerError("import bundle datasets must be a list")

        created_datasets = 0
        upserted_records = 0
        existing_ids = {item["dataset_id"] for item in self.list_datasets()}
        for item in datasets:
            if not isinstance(item, dict):
                raise DataManagerError("invalid dataset entry")
            dataset_id = _validate_id(str(item.get("id", "")), "dataset_id")
            if dataset_id not in existing_ids:
                self.create_dataset(dataset_id, str(item.get("description", "")))
                existing_ids.add(dataset_id)
                created_datasets += 1
            records = item.get("records", [])
            if not isinstance(records, list):
                raise DataManagerError("records must be a list")
            for record in records:
                if not isinstance(record, dict):
                    raise DataManagerError("invalid record entry")
                record_id = _validate_id(str(record.get("record_id", record.get("id", ""))), "record_id")
                data = record.get("data")
                self.put_record(dataset_id, record_id, data)
                upserted_records += 1
        return {"created_datasets": created_datasets, "upserted_records": upserted_records}

    def verify(self, dataset_id: str | None = None) -> dict[str, Any]:
        datasets = [self.get_dataset(dataset_id)] if dataset_id else self.list_datasets()
        issues: list[dict[str, str]] = []
        checked = 0
        for dataset in datasets:
            for record in self.list_records(dataset["dataset_id"]):
                checked += 1
                try:
                    canonical = _canonical_json(record["data"])
                except DataManagerError as exc:
                    issues.append(
                        {
                            "dataset_id": dataset["dataset_id"],
                            "record_id": record["record_id"],
                            "issue": str(exc),
                        }
                    )
                    continue
                if _checksum(canonical) != record["checksum"]:
                    issues.append(
                        {
                            "dataset_id": dataset["dataset_id"],
                            "record_id": record["record_id"],
                            "issue": "checksum mismatch",
                        }
                    )
        return {"ok": not issues, "checked_records": checked, "issues": issues}

    @staticmethod
    def _record_dict(dataset_id: str, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "dataset_id": dataset_id,
            "record_id": row["record_id"],
            "data": json.loads(row["payload"]),
            "checksum": row["checksum"],
            "revision": int(row["revision"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
