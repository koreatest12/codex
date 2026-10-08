"""Exhaustive tests of secret source precedence, errors, and safe diagnostics."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from secret_config import require_secret


class SecretConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.secret = Path(self.temporary.name) / "key-file"
        self.secret.write_text("test-file-value\n", encoding="utf-8")

    def test_value_only(self):
        self.assertEqual(
            "only-in-environment",
            require_secret("SESSION_SECRET", "SESSION_SECRET_FILE",
                           environ={"SESSION_SECRET": " only-in-environment "}),
        )

    def test_file_only(self):
        self.assertEqual(
            "test-file-value",
            require_secret("SESSION_SECRET", "SESSION_SECRET_FILE",
                           environ={"SESSION_SECRET_FILE": str(self.secret)}),
        )

    def test_explicitly_blank_file_setting_does_not_conflict(self):
        self.assertEqual(
            "only-in-environment",
            require_secret("SESSION_SECRET", "SESSION_SECRET_FILE",
                           environ={"SESSION_SECRET": "only-in-environment",
                                    "SESSION_SECRET_FILE": ""}),
        )

    def test_both_sources_rejected_even_when_values_match(self):
        with self.assertRaisesRegex(RuntimeError, "configure only one of"):
            require_secret(
                "SESSION_SECRET", "SESSION_SECRET_FILE",
                environ={"SESSION_SECRET": "test-file-value",
                         "SESSION_SECRET_FILE": str(self.secret)},
            )

    def test_missing_file_rejected_without_exposing_paths(self):
        with self.assertRaisesRegex(RuntimeError, "unable to read SESSION_SECRET_FILE"):
            require_secret("SESSION_SECRET", "SESSION_SECRET_FILE",
                           environ={"SESSION_SECRET_FILE": str(self.secret) + "-missing"})

    def test_empty_file_rejected(self):
        self.secret.write_text("\n \t", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "empty secret"):
            require_secret("SESSION_SECRET", "SESSION_SECRET_FILE",
                           environ={"SESSION_SECRET_FILE": str(self.secret)})

    def test_missing_everything_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "must be configured"):
            require_secret("SESSION_SECRET", "SESSION_SECRET_FILE", environ={})

    def test_file_cannot_be_used_as_weak_password_fallback(self):
        self.secret.write_text("test-other-key", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            require_secret(
                "DATA_ENCRYPTION_KEY", "DATA_ENCRYPTION_KEY_FILE",
                environ={
                    "DATA_ENCRYPTION_KEY": "should-not-be-used",
                    "DATA_ENCRYPTION_KEY_FILE": str(self.secret),
                },
            )

    def test_reads_provided_environment_not_runner_environment(self):
        with patch.dict(os.environ, {
            "SESSION_SECRET": "ambient-runner-value",
            "SESSION_SECRET_FILE": str(self.secret),
        }):
            result = require_secret(
                "SESSION_SECRET", "SESSION_SECRET_FILE",
                environ={"SESSION_SECRET": "only-from-fixture"},
            )
        self.assertEqual("only-from-fixture", result)


if __name__ == "__main__":
    unittest.main()
