"""Server-startup regression tests using real imports in isolated subprocesses.

Reproduces the historical CI collision without inheriting GitHub's file-based
secret variables. A conflicting configuration MUST still fail closed.
"""
import base64
import os
import secrets
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PAIRS = (
    ("SESSION_SECRET", "SESSION_SECRET_FILE"),
    ("WEBAUTHN_BOOTSTRAP_TOKEN", "WEBAUTHN_BOOTSTRAP_TOKEN_FILE"),
    ("DATA_ENCRYPTION_KEY", "DATA_ENCRYPTION_KEY_FILE"),
)


class ServerStartupSecretsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        values = {
            "SESSION_SECRET": "ci-secret-" + secrets.token_urlsafe(32),
            "WEBAUTHN_BOOTSTRAP_TOKEN": secrets.token_urlsafe(32),
            "DATA_ENCRYPTION_KEY": base64.urlsafe_b64encode(
                secrets.token_bytes(32)
            ).decode("ascii"),
        }
        self.values = values
        self.files = {}
        for name, _ in PAIRS:
            path = folder / name.lower()
            path.write_text(values[name], encoding="utf-8")
            self.files[name] = path

        # Explicitly remove any inherited direct AND file-based variables,
        # regardless of whether the workflow runner configured them.
        self.env = os.environ.copy()
        for direct, file_key in PAIRS:
            self.env.pop(direct, None)
            self.env.pop(file_key, None)
        self.env.pop("ADMIN_ACCOUNT_FILE", None)
        self.env.update({
            "PYTHONPATH": str(ROOT / "app"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "WEBAUTHN_RP_ID": "localhost",
            "WEBAUTHN_ORIGIN": "http://localhost:8080",
            "WEBAUTHN_DB_PATH": str(folder / "webauthn.db"),
            "MANAGED_DATA_DB_PATH": str(folder / "managed-data.db"),
        })

    def start(self, extra):
        env = {**self.env, **extra}
        return subprocess.run(
            [sys.executable, "-c", "import server; print('SERVER_IMPORT_OK')"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )

    def test_direct_values_launch_without_inherited_file_paths(self):
        result = self.start(self.values)
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        self.assertIn("SERVER_IMPORT_OK", result.stdout)

    def test_three_file_backed_secrets_launch(self):
        result = self.start({
            file_key: str(self.files[direct])
            for direct, file_key in PAIRS
        })
        self.assertEqual(result.returncode, 0, result.stderr[-1500:])
        self.assertIn("SERVER_IMPORT_OK", result.stdout)

    def test_each_duplicate_source_fails_closed(self):
        for conflicted, conflict_file in PAIRS:
            with self.subTest(secret=conflicted):
                env = dict(self.values)
                env[conflict_file] = str(self.files[conflicted])
                result = self.start(env)
                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    f"configure only one of {conflicted} or {conflict_file}",
                    result.stderr,
                )
                self.assertNotIn(self.values[conflicted], result.stderr)

    def test_missing_file_does_not_fallback_to_insecure_default(self):
        env = dict(self.values)
        env.pop("SESSION_SECRET")
        env["SESSION_SECRET_FILE"] = str(Path(self.temp.name) / "missing")
        result = self.start(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unable to read SESSION_SECRET_FILE", result.stderr)

    def test_missing_secret_rejects_startup(self):
        env = dict(self.values)
        env.pop("SESSION_SECRET")
        result = self.start(env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SESSION_SECRET or SESSION_SECRET_FILE must be configured",
                      result.stderr)


if __name__ == "__main__":
    unittest.main()
