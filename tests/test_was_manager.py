"""No-host, no-Docker regression tests for the WAS lifecycle manager."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("was_manager", ROOT / "scripts" / "was-manager.py")
WAS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WAS)


class SimulatedWas(WAS.WasManager):
    def __init__(self, root, fail_archive=False):
        super().__init__(root)
        self.calls = []
        self.fail_archive = fail_archive

    def docker(self):
        self.calls.append(["docker", "info (stub)"])

    def config(self):
        return {
            "services": {"web": {"image": "codex-linux-server:test"}},
            "volumes": {"security-data": {"name": "codex_security-data"}},
        }

    def image(self, config):
        return config["services"]["web"]["image"]

    def volume(self, config):
        return config["volumes"]["security-data"]["name"]

    def run(self, args, *, capture=False):
        self.calls.append(args)
        if args[-3:] == ["ps", "-q", "web"]:
            return "test-container"
        if args[:3] == ["docker", "inspect", "--format"]:
            return "true"
        if args[:2] == ["docker", "run"]:
            if self.fail_archive:
                raise WAS.WasError("Simulated tar failure")
            (self.root / "backups" / args[-1]).write_bytes(b"test archive")
        return ""


class WasManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "secrets").mkdir()

    def test_missing_config_cannot_start(self):
        manager = WAS.WasManager(self.root)
        with self.assertRaisesRegex(WAS.WasError, "Missing .env"):
            manager.secrets()

    def test_init_refuses_to_overwrite_existing_secrets(self):
        (self.root / "secrets" / "session_secret").write_text("existing")
        with self.assertRaisesRegex(WAS.WasError, "refusing to overwrite"):
            WAS.WasManager(self.root).init("localhost", "http://localhost:8080")

    def test_secret_checks_reject_symlinks(self):
        (self.root / ".env").write_text("WEBAUTHN_RP_ID=localhost")
        for name in WAS.SECRET_NAMES:
            (self.root / "secrets" / name).write_text("secret", encoding="utf-8")
        (self.root / "secrets" / "session_secret").unlink()
        (self.root / "secrets" / "session_secret").symlink_to(self.root / ".env")
        with self.assertRaisesRegex(WAS.WasError, "session_secret"):
            WAS.WasManager(self.root).secrets()

    def test_invalid_volume_identifier_is_rejected(self):
        manager = WAS.WasManager(self.root)
        with self.assertRaisesRegex(WAS.WasError, "Invalid persistent volume"):
            manager.volume({"volumes": {"security-data": {"name": "../outside"}}})

    def test_backup_preserves_volume_and_restarts_running_service(self):
        manager = SimulatedWas(self.root)
        output = manager.backup()
        self.assertTrue(output.is_file())
        self.assertGreater(output.stat().st_size, 0)
        actions = [tuple(x) for x in manager.calls]
        self.assertIn(tuple([*manager.compose(), "stop", "web"]), actions)
        self.assertIn(tuple([*manager.compose(), "start", "web"]), actions)
        self.assertFalse(any("rm" in x or "-v" in x for x in manager.calls))
        self.assertEqual(list((self.root / "backups").glob("*.partial")), [])

    def test_backup_failure_restarts_service_and_removes_partial(self):
        manager = SimulatedWas(self.root, fail_archive=True)
        with self.assertRaisesRegex(WAS.WasError, "Simulated tar failure"):
            manager.backup()
        self.assertIn([*manager.compose(), "start", "web"], manager.calls)
        self.assertEqual(list((self.root / "backups").iterdir()), [])

    def test_logs_tail_validation(self):
        cli = WAS.parser()
        self.assertEqual(cli.parse_args(["logs", "--tail", "20"]).tail, 20)
        self.assertTrue(cli.parse_args(["logs", "--follow"]).follow)

    def test_cli_help_is_available_without_docker(self):
        with mock.patch("sys.argv", ["was-manager.py", "--help"]):
            with self.assertRaises(SystemExit) as result:
                WAS.parser().parse_args()
            self.assertEqual(result.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
