import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from admin_auth import AdminAccount, make_account


class AdminAccountTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            import json
            path = Path(directory) / "account"
            credential = make_account("admin", "test-generated-long-password-123456")
            path.write_text(json.dumps(credential), encoding="utf-8")
            account = AdminAccount.from_file(str(path))
            self.assertEqual(account.username, "admin")
            self.assertTrue(account.verify("admin", "test-generated-long-password-123456"))
            self.assertFalse(account.verify("admin", "incorrect-password-123456"))
            self.assertFalse(account.verify("other", "test-generated-long-password-123456"))
            self.assertNotIn("test-generated-long-password-123456", path.read_text())

    def test_reject_short_password_username(self):
        with self.assertRaises(ValueError):
            make_account("admin", "123456789")
        with self.assertRaises(ValueError):
            make_account("a", "test-generated-long-password-123456")

    def test_tampered_hash_rejected(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "account"
            data = make_account("admin", "test-generated-long-password-123456")
            data["algorithm"] = "plaintext"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                AdminAccount.from_file(str(path))

    def test_oversized_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "account"
            path.write_bytes(b"X" * 4097)
            with self.assertRaises(ValueError):
                AdminAccount.from_file(str(path))


if __name__ == "__main__":
    unittest.main()
