"""Authenticated integration without registering or exposing real credentials."""
import base64
import importlib
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class GameRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        cls.env = patch.dict(os.environ, {
            "SESSION_SECRET": secrets.token_urlsafe(40),
            "SESSION_SECRET_FILE": "",
            "WEBAUTHN_BOOTSTRAP_TOKEN": secrets.token_urlsafe(40),
            "WEBAUTHN_BOOTSTRAP_TOKEN_FILE": "",
            "DATA_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
            "DATA_ENCRYPTION_KEY_FILE": "",
            "WEBAUTHN_RP_ID": "localhost",
            "WEBAUTHN_ORIGIN": "http://localhost:8080",
            "WEBAUTHN_DB_PATH": str(root / "webauthn.db"),
            "MANAGED_DATA_DB_PATH": str(root / "managed-data.db"),
        })
        cls.env.start()
        cls.server = importlib.import_module("server")
        cls.server.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.directory.cleanup()

    def setUp(self):
        self.client = self.server.app.test_client()

    def authenticate_test_session(self):
        # Only a test fixture; production sessions are set by verified WebAuthn.
        with self.client.session_transaction() as session:
            session["authenticated"] = True

    def test_game_redirects_unauthenticated_users(self):
        response = self.client.get("/game/")
        self.assertEqual(302, response.status_code)
        self.assertEqual("/", response.headers["Location"])

    def test_monitor_and_private_api_require_authentication(self):
        for url in ("/api/game/health", "/api/private-values", "/api/data/datasets"):
            self.assertEqual(403, self.client.get(url).status_code)

    def test_authenticated_game_preserves_csp_and_loads_assets(self):
        self.authenticate_test_session()
        response = self.client.get("/game/")
        self.assertEqual(200, response.status_code)
        self.assertIn("분식 러시", response.get_data(as_text=True))
        self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", response.headers["Content-Security-Policy"])
        for file in ("engine.js", "game.js", "style.css"):
            with self.client.get("/static/bunsik-rush/" + file) as asset:
                self.assertEqual(200, asset.status_code)

    def test_monitor_returns_only_safe_health_fields(self):
        self.authenticate_test_session()
        response = self.client.get("/api/game/health")
        self.assertEqual(200, response.status_code)
        self.assertEqual("no-store", response.headers["Cache-Control"])
        data = response.get_json()
        self.assertEqual("bunsik-rush", data["service"])
        self.assertEqual("ok", data["status"])
        self.assertEqual("browser", data["gameExecution"])
        self.assertEqual({"service", "status", "version", "time", "runtime", "gameExecution"}, set(data))
        self.assertIn("time", data)

    def test_music_supports_browser_range_requests(self):
        response = self.client.get("/static/bunsik-rush/bgm.mp3", headers={"Range": "bytes=0-127"})
        self.assertEqual(206, response.status_code)
        self.assertEqual(128, len(response.get_data()))
        self.assertIn("bytes 0-127/", response.headers["Content-Range"])
        response.close()

    def test_home_shows_game_link_only_after_authentication(self):
        self.assertNotIn('/game/', self.client.get('/').get_data(as_text=True))
        self.authenticate_test_session()
        self.assertIn('/game/', self.client.get('/').get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
