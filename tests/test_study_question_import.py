"""Regression tests for bulk 2027 exam question import. No production databases."""
import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("study_question_import", PROJECT / "scripts" / "study-question-import.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StudySeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "questions.db"
        self.seed = PROJECT / "data" / "study" / "security-exam-2027.json"

    def test_content_is_full_coverage_original_and_valid(self):
        data = json.loads(self.seed.read_text(encoding="utf-8"))
        rows = MODULE.load_seed(self.seed)
        self.assertEqual(120, len(rows))
        parts = Counter(item["exam_part"] for _, _, item in rows)
        self.assertEqual({"필기": 100, "실기": 20}, dict(parts))
        objective = Counter(item["subject"] for _, _, item in rows if item["exam_part"] == "필기")
        self.assertEqual({s: 20 for s in ["시스템 보안", "네트워크 보안", "어플리케이션 보안", "정보보안 일반", "정보보안 관리 및 법규"]}, dict(objective))
        self.assertFalse(data["official_exam_questions"])
        self.assertEqual(len(set(key for _, key, _ in rows)), len(rows))
        self.assertTrue(all(row["source_url"].startswith("https://") for _, _, row in rows))

    def test_default_dry_run_has_no_side_effects(self):
        result = MODULE.import_seed(self.seed, self.db)
        self.assertEqual("dry-run", result["mode"])
        self.assertEqual(120, result["validated"])
        self.assertFalse(self.db.exists())

    def test_import_draft_only_and_idempotency_with_backup(self):
        first = MODULE.import_seed(self.seed, self.db, apply=True)
        self.assertEqual(120, first["inserted"])
        bank = MODULE.QuestionBank(self.db)
        with bank.connect() as db:
            states = db.execute("SELECT status, COUNT(*) FROM questions GROUP BY status").fetchall()
        self.assertEqual([("draft", 120)], [(r[0], r[1]) for r in states])
        backup = self.root / "backup"
        backup.mkdir()
        second = MODULE.import_seed(self.seed, self.db, apply=True, backup_dir=backup)
        self.assertEqual(120, second["already_present"])
        self.assertEqual(0, second["inserted"])
        self.assertEqual(1, len(list(backup.glob("*.sqlite3"))))
        with bank.connect() as db:
            self.assertEqual(120, db.execute("SELECT COUNT(*) FROM questions").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM questions WHERE status='published'").fetchone()[0])

    def test_refuse_missing_existing_db_backup(self):
        MODULE.import_seed(self.seed, self.db, apply=True)
        with self.assertRaisesRegex(MODULE.ImportErrorStudy, "backup"):
            MODULE.import_seed(self.seed, self.db, apply=True)

    def test_bad_content_is_rejected_before_write(self):
        data = json.loads(self.seed.read_text(encoding="utf-8"))
        data["items"][1]["key"] = data["items"][0]["key"]
        invalid = self.root / "invalid.json"
        invalid.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.ImportErrorStudy, "duplicate"):
            MODULE.import_seed(invalid, self.db, apply=True)
        self.assertFalse(self.db.exists())

    def test_import_preserves_edited_item(self):
        rows = MODULE.load_seed(self.seed)
        MODULE.import_seed(self.seed, self.db, apply=True)
        id_, _, _ = rows[0]
        bank = MODULE.QuestionBank(self.db)
        with bank.connect() as db:
            db.execute("UPDATE questions SET prompt=?, revision=99, status='published' WHERE id=?",
                       ("사용자 검토 후 승인한 별도 문제", id_))
        backup = self.root / "backup3"
        backup.mkdir()
        MODULE.import_seed(self.seed, self.db, apply=True, backup_dir=backup)
        self.assertEqual(99, bank.get(id_)["revision"])
        self.assertEqual("published", bank.get(id_)["status"])
        self.assertEqual("사용자 검토 후 승인한 별도 문제", bank.get(id_)["prompt"])


if __name__ == "__main__":
    unittest.main()
