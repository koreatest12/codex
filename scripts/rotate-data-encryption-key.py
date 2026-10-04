#!/usr/bin/env python3
import argparse
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from privacy import PrivacyCipher  # noqa: E402


def read_key(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise SystemExit(f"empty key file: {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-encrypt private_values with a new AES-256-GCM key.")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--old-key-file", required=True, type=Path)
    parser.add_argument("--new-key-file", required=True, type=Path)
    args = parser.parse_args()

    old_cipher = PrivacyCipher(read_key(args.old_key_file))
    new_cipher = PrivacyCipher(read_key(args.new_key_file))

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute("SELECT record_id, kind, nonce, ciphertext FROM private_values").fetchall()
        for row in rows:
            payload = old_cipher.decrypt(row["record_id"], row["kind"], bytes(row["nonce"]), bytes(row["ciphertext"]))
            nonce, ciphertext = new_cipher.encrypt(row["record_id"], row["kind"], payload["label"], payload["value"])
            connection.execute(
                "UPDATE private_values SET nonce=?, ciphertext=?, updated_at=CURRENT_TIMESTAMP WHERE record_id=?",
                (sqlite3.Binary(nonce), sqlite3.Binary(ciphertext), row["record_id"]),
            )
        connection.commit()
        print(f"Re-encrypted {len(rows)} private values.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
