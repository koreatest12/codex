#!/usr/bin/env python3
"""Import hand-authored study exercises into the existing SQLite question bank.

By default validates the complete file and reports counts without writing.
--apply explicitly imports as DRAFT, never publishes and never overwrites edits.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from question_bank import QuestionBank, QuestionError, FIELDS, _normalize  # noqa: E402


class ImportErrorStudy(ValueError):
    pass


def load_seed(seed_path):
    data = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ImportErrorStudy("schema_version must be 1")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ImportErrorStudy("seed must have a nonempty items list")
    results = []
    keys = set()
    for n, row in enumerate(items, 1):
        if not isinstance(row, dict) or set(row) != set(FIELDS) | {"key"}:
            raise ImportErrorStudy(f"row {n}: expected key plus exact question fields")
        key = row["key"]
        if not isinstance(key, str) or len(key) > 96 or not key.startswith("SEC27-"):
            raise ImportErrorStudy(f"row {n}: invalid SEC27- key")
        if key in keys:
            raise ImportErrorStudy(f"duplicate key: {key}")
        keys.add(key)
        try:
            item = _normalize({field: row[field] for field in FIELDS})
        except QuestionError as error:
            raise ImportErrorStudy(f"row {n} / {key}: {error}") from error
        if not item["source_url"]:
            raise ImportErrorStudy(f"row {n}: source_url is required")
        identifier = "study27_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        results.append((identifier, key, item))
    return results


def import_seed(seed_path, db_path, apply=False, backup_dir=None):
    rows = load_seed(seed_path)  # Validate the entire batch *before* any writes.
    result = {
        "validated": len(rows), "inserted": 0, "already_present": 0,
        "mode": "apply" if apply else "dry-run", "all_new_status": "draft"
    }
    if not apply:
        return result

    target = Path(db_path)
    existed = target.is_file()
    if existed and not backup_dir:
        raise ImportErrorStudy("existing database requires --backup-dir")
    if not existed and not target.parent.is_dir():
        raise ImportErrorStudy("database parent directory must already exist")
    if existed:
        backup = Path(backup_dir)
        if not backup.is_dir():
            raise ImportErrorStudy("backup directory must already exist")
        if backup.resolve() == target.parent.resolve():
            raise ImportErrorStudy("use a separate backup directory")
        backup_name = target.stem + "-" + hashlib.sha256(
            (str(Path(seed_path).resolve()) + str(target.resolve())).encode()
        ).hexdigest()[:10] + ".sqlite3"
        # Refuse overwrites of an old backup: an operator must choose a new dir.
        backup_path = backup / backup_name
        if backup_path.exists():
            raise ImportErrorStudy("backup filename exists; use a new backup directory")
        with sqlite3.connect(str(target), timeout=10) as source:
            with sqlite3.connect(str(backup_path), timeout=10) as destination:
                source.backup(destination)
        result["backup_created"] = str(backup_path)

    bank = QuestionBank(target)
    bank.init_schema()
    with bank.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for identifier, key, item in rows:
            existing = db.execute("SELECT source_type FROM questions WHERE id=?", (identifier,)).fetchone()
            if existing:
                if existing["source_type"] != "self-authored":
                    raise ImportErrorStudy(f"unexpected existing ID for {key}")
                result["already_present"] += 1
                continue
            db.execute("""
                INSERT INTO questions
                    (id, exam_part, subject, kind, topic, prompt, options_json,
                     correct_index, model_answer, explanation, source_url,
                     source_type, difficulty, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'self-authored', ?, 'draft')
            """, (
                identifier, item["exam_part"], item["subject"], item["kind"],
                item["topic"], item["prompt"],
                json.dumps(item["options"], ensure_ascii=False), item["correct_index"],
                item["model_answer"], item["explanation"], item["source_url"],
                item["difficulty"],
            ))
            result["inserted"] += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default=str(ROOT / "data/study/security-exam-2027.json"))
    parser.add_argument("--db", required=True, help="SQLite question-bank.db path")
    parser.add_argument("--apply", action="store_true", help="Explicitly insert draft questions")
    parser.add_argument("--backup-dir", help="Existing directory for pre-import DB backup")
    args = parser.parse_args()
    try:
        output = import_seed(args.seed, args.db, apply=args.apply, backup_dir=args.backup_dir)
    except (ValueError, OSError, sqlite3.DatabaseError) as error:
        print("Import rejected: " + str(error), file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
