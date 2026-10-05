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

    def test_delete_preserves_generation_and_prevents_id_reuse(self):
        row = self.manager.put_record("biff-2026", "deleted", {"value": 1})
        deleted = self.manager.delete_record(
            "biff-2026",
            "deleted",
            expected_revision=row["revision"],
        )
        self.assertEqual(2, deleted["tombstone_revision"])
        with self.assertRaises(RevisionConflict):
            self.manager.put_record("biff-2026", "deleted", {"value": 2})
        revisions = [
            item["record_revision"]
            for item in self.manager.history("biff-2026", "deleted")
        ]
        self.assertEqual([1, 2], revisions)

    def test_import_is_atomic_when_late_record_is_invalid(self):
        bundle = {
            "schema_version": 1,
            "datasets": [
                {
                    "id": "atomic-new",
                    "description": "test",
                    "records": [
                        {"id": "good", "data": {"value": 1}},
                        {"id": "bad", "data": {"note": "contact person@example.com"}},
                    ],
                }
            ],
        }
        with self.assertRaises(SensitiveDataError):
            self.manager.import_bundle(bundle)
        dataset_ids = {item["dataset_id"] for item in self.manager.list_datasets()}
        self.assertNotIn("atomic-new", dataset_ids)

    def test_update_dataset_requires_matching_revision(self):
        current = self.manager.get_dataset("biff-2026")
        updated = self.manager.update_dataset(
            "biff-2026",
            "updated public itinerary",
            expected_revision=current["revision"],
        )
        self.assertEqual("updated public itinerary", updated["description"])
        with self.assertRaises(RevisionConflict):
            self.manager.update_dataset(
                "biff-2026",
                "stale",
                expected_revision=current["revision"],
            )

    def test_private_ref_is_allowed(self):
        row = self.manager.put_record(
            "biff-2026",
            "booking-ref",
            {"private_ref": "vault-record-id", "type": "srt"},
        )
        self.assertEqual("vault-record-id", row["data"]["private_ref"])

    def test_import_preserves_existing_description_when_omitted(self):
        current = self.manager.get_dataset("biff-2026")
        self.assertEqual("public itinerary data", current["description"])

        result = self.manager.import_bundle(
            {
                "schema_version": 1,
                "datasets": [
                    {
                        "id": "biff-2026",
                        "records": [
                            {"id": "new-record", "data": {"value": 1}},
                        ],
                    }
                ],
            }
        )

        after = self.manager.get_dataset("biff-2026")
        self.assertEqual("public itinerary data", after["description"])
        self.assertEqual(0, result["updated_datasets"])
        self.assertEqual(1, result["changed_records"])

    def test_export_and_import(self):
        self.manager.put_record("biff-2026", "movie", {"title": "자필"})
        bundle = self.manager.export_bundle()

        second_db = Path(self.temp.name) / "second.db"
        second = DataManager(second_db)
        second.init_schema()
        result = second.import_bundle(bundle)
        self.assertEqual(1, result["created_datasets"])
        self.assertEqual(1, result["changed_records"])
        self.assertEqual("자필", second.get_record("biff-2026", "movie")["data"]["title"])


if __name__ == "__main__":
    unittest.main()
