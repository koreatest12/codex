import json
import tempfile
import unittest
from pathlib import Path

from data_manager import (
    DataManager,
    RevisionConflict,
    SensitiveDataError,
)


class DataManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "managed.db"
        self.manager = DataManager(self.db)
        self.manager.init_schema()
        self.manager.create_dataset("biff-2026", "public itinerary data")

    def tearDown(self):
        self.temp.cleanup()

    def test_create_update_history_and_verify(self):
        created = self.manager.put_record(
            "biff-2026",
            "opening",
            {"date": "2026-10-06", "time": "18:00", "venue": "영화의전당"},
        )
        self.assertEqual(1, created["revision"])

        updated = self.manager.put_record(
            "biff-2026",
            "opening",
            {"date": "2026-10-06", "time": "19:00", "venue": "영화의전당"},
            expected_revision=1,
        )
        self.assertEqual(2, updated["revision"])
        self.assertEqual(2, len(self.manager.history("biff-2026", "opening")))
        self.assertTrue(self.manager.verify()["ok"])

    def test_identical_update_is_idempotent(self):
        first = self.manager.put_record("biff-2026", "same", {"value": 1})
        second = self.manager.put_record(
            "biff-2026",
            "same",
            {"value": 1},
            expected_revision=1,
        )
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(1, len(self.manager.history("biff-2026", "same")))

    def test_dataset_description_rejects_contact_data(self):
        with self.assertRaises(SensitiveDataError):
            self.manager.create_dataset("private-description", "owner test@example.com")

    def test_optimistic_revision_conflict(self):
        self.manager.put_record("biff-2026", "x", {"value": 1})
        with self.assertRaises(RevisionConflict):
            self.manager.put_record(
                "biff-2026",
                "x",
                {"value": 2},
                expected_revision=0,
            )

    def test_rejects_sensitive_keys_and_contacts(self):
        with self.assertRaises(SensitiveDataError):
            self.manager.put_record(
                "biff-2026",
                "private",
                {"phone": "010-1234-5678"},
            )
        with self.assertRaises(SensitiveDataError):
            self.manager.put_record(
                "biff-2026",
                "private2",
                {"note": "test@example.com"},
            )

    def test_private_ref_is_allowed(self):
        row = self.manager.put_record(
            "biff-2026",
            "booking-ref",
            {"private_ref": "vault-record-id", "type": "srt"},
        )
        self.assertEqual("vault-record-id", row["data"]["private_ref"])

    def test_export_and_import(self):
        self.manager.put_record("biff-2026", "movie", {"title": "자필"})
        bundle = self.manager.export_bundle()

        second_db = Path(self.temp.name) / "second.db"
        second = DataManager(second_db)
        second.init_schema()
        result = second.import_bundle(bundle)
        self.assertEqual(1, result["created_datasets"])
        self.assertEqual("자필", second.get_record("biff-2026", "movie")["data"]["title"])


if __name__ == "__main__":
    unittest.main()
