"""Integration gates: password never replaces the hardware security key."""
import base64
import importlib
import json
import os
import secrets
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from admin_auth import make_account


class AdminServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        folder = Path(cls.temporary.name)
        cls.password = "only-for-test-Password-1234567890!"
        cls.account_file = folder / "admin_account"
        cls.account_file.write_text(
            json.dumps(make_account("admin", cls.password)), encoding="utf-8"
        )
        options = {
            "SESSION_SECRET": "integration-test-" + secrets.token_urlsafe(40),
            "WEBAUTHN_RP_ID": "localhost",
            "WEBAUTHN_ORIGIN": "http://localhost:8080",
            "WEBAUTHN_BOOTSTRAP_TOKEN": secrets.token_urlsafe(30),
            "DATA_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
            "WEBAUTHN_DB_PATH": str(folder / "webauthn.db"),
            "MANAGED_DATA_DB_PATH": str(folder / "managed-data.db"),
            "ADMIN_ACCOUNT_FILE": str(cls.account_file),
        }
        cls.env = patch.dict(os.environ, options)
        cls.env.start()
        sys.modules.pop("server", None)
        cls.server = importlib.import_module("server")
        cls.server.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("server", None)
        cls.env.stop()
        cls.temporary.cleanup()

    def setUp(self):
        self.client = self.server.app.test_client()
        with self.server.db() as conn:
            conn.execute("DELETE FROM admin_login_failures")

    def test_default_denial_and_no_password_bypass(self):
        self.assertEqual(403, self.client.get("/api/system/status").status_code)
        self.assertEqual(403, self.client.get("/api/security/credentials").status_code)
        self.assertEqual(403, self.client.get("/api/private-values").status_code)
        self.assertEqual(403, self.client.post("/api/security/authenticate/options", json={}).status_code)
        self.assertEqual(403, self.client.post("/api/security/register/options", json={}).status_code)
        info = self.client.get("/api/security/status").get_json()
        self.assertTrue(info["password_required"])
        self.assertFalse(info["authenticated"])
        self.assertFalse(info["password_verified"])

    def test_password_first_then_hardware_key_still_required(self):
        self.assertEqual(
            401,
            self.client.post("/api/security/account/login", json={
                "username": "admin", "password": "wrong-password-long-enough"
            }).status_code,
        )
        good = self.client.post("/api/security/account/login", json={
            "username": "admin", "password": self.password
        })
        self.assertEqual(200, good.status_code)
        self.assertEqual("webauthn", good.get_json()["next_step"])
        info = self.client.get("/api/security/status").get_json()
        self.assertTrue(info["password_verified"])
        self.assertFalse(info["authenticated"])
        self.assertEqual(403, self.client.get("/api/system/status").status_code)

        # Emulate *only* a successful WebAuthn session marker to exercise
        # authorization gates; actual key signature is verified by existing flow.
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True
        self.assertEqual(200, self.client.get("/api/system/status").status_code)
        self.assertEqual(200, self.client.get("/api/security/credentials").status_code)
        result = self.client.get("/api/system/status").get_json()
        self.assertEqual("admin", result["admin_username"])
        self.assertEqual("password+webauthn", result["authentication"])
        self.assertTrue(result["database_present"])
        self.assertGreaterEqual(result["storage_bytes_total"], result["storage_bytes_used"])

    def test_without_password_marker_fake_key_session_is_denied(self):
        with self.client.session_transaction() as sess:
            sess["authenticated"] = True
        self.assertEqual(403, self.client.get("/api/system/status").status_code)

    def test_logout_revokes_both_steps(self):
        self.client.post("/api/security/account/login", json={
            "username": "admin", "password": self.password
        })
        self.assertEqual(200, self.client.post("/api/security/logout", json={}).status_code)
        self.assertEqual(403, self.client.get("/api/system/status").status_code)
        self.assertFalse(self.client.get("/api/security/status").get_json()["password_verified"])

    def test_five_failures_lock_password_stage(self):
        for _ in range(5):
            response = self.client.post("/api/security/account/login", json={
                "username": "admin", "password": "bad-login-credential"
            })
            self.assertEqual(401, response.status_code)
        self.assertEqual(
            429,
            self.client.post("/api/security/account/login", json={
                "username": "admin", "password": self.password
            }).status_code
        )


if __name__ == "__main__":
    unittest.main()
