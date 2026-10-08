"""Container-retention regression tests. No Docker daemon or network is used.

Run from the repository root with:
    python3 -m unittest discover -s tests -p test_container_scripts.py -v

Every script runs with a restricted PATH containing only a strict Docker fake,
a no-op sleep, grep, and a small allowlist of filesystem utilities. Unknown Docker operations fail the test, even when the
shell script suppresses their exit status. Container IDs and lifecycle state
are simulated so command ordering and accidental name reuse are observable.
"""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTAINER_ID = "a1" * 32
IMAGE_ID = "sha256:" + "b2" * 32
BASH = shutil.which("bash")
GREP = shutil.which("grep")


FAKE_DOCKER = r'''
import json
import os
from pathlib import Path
import sys

config = json.loads(Path(os.environ["FAKE_DOCKER_CONFIG"]).read_text())
state_path = Path(os.environ["FAKE_DOCKER_STATE"])
state = json.loads(state_path.read_text())
args = sys.argv[1:]
with Path(os.environ["FAKE_DOCKER_LOG"]).open("a") as log:
    log.write(json.dumps(args) + "\n")

def save():
    state_path.write_text(json.dumps(state))

def reject(reason):
    with Path(os.environ["FAKE_DOCKER_REJECTIONS"]).open("a") as log:
        log.write(reason + ": " + json.dumps(args) + "\n")
    print("FAKE DOCKER REJECTED: " + reason, file=sys.stderr)
    sys.exit(97)

def fail(phase):
    if config.get("failure") == phase:
        print("simulated " + phase + " failure", file=sys.stderr)
        sys.exit(1)

container_id = config["id"]
name = config["name"]
base_image = config["base_image"]
server_image = config["server_image"]
failure = config.get("failure")
destructive = {"rm", "rmi", "stop", "restart", "kill", "prune", "remove"}
if not args or any(arg in destructive or arg == "--rm" or arg.startswith("--rm=")
                   for arg in args):
    reject("destructive or empty Docker command")

if args == ["ps", "-a", "--format", "{{.Names}}"]:
    fail("preflight")
    print("\n".join(item["name"] for item in state["existing"]))
elif args == ["pull", base_image]:
    fail("pull")
    print("fake image pulled")
elif (len(args) == 9 and args[:2] == ["build", "--iidfile"]
      and args[3:] == ["--pull", "--build-arg", "BASE_IMAGE=" + base_image,
                       "-t", server_image, "."]):
    fail("build")
    iidfile = Path(args[2])
    if (iidfile.name != "image-id" or not iidfile.parent.is_dir()
            or iidfile.parent.parent != Path(os.environ["TMPDIR"])
            or iidfile.parent.stat().st_mode & 0o077):
        reject("iidfile must be in an existing private temporary directory")
    state["iidfile"] = str(iidfile)
    state["built"] = config["image_id"]
    # Simulate another build moving the mutable tag immediately afterward.
    state["tag_image_id"] = "sha256:" + "c3" * 32
    save()
    if failure != "missing_iid":
        iidfile.write_text(config.get("returned_iid", config["image_id"]) + "\n")
    print("fake image built")
elif args == ["volume", "create", config["volume"]]:
    fail("volume")
    state["volume_created"] = True
    save()
    print(config["volume"])
elif args == config["create_args"]:
    if state["built"] != args[-1] or not state["volume_created"]:
        reject("create must use this build's image ID after creating its volume")
    if failure == "race":
        state["existing"].append({"name": name, "status": "running"})
        state["race_seen"] = True
        save()
        print("simulated concurrent name collision", file=sys.stderr)
        sys.exit(1)
    fail("create")
    if any(item["name"] == name for item in state["existing"]):
        reject("attempted creation despite an existing exact name")
    state["created"] = container_id
    save()
    print(config.get("returned_container_id", container_id))
elif args == ["start", container_id]:
    if state["created"] != container_id:
        reject("start before creation")
    fail("start")
    state["started"] = True
    save()
    print(container_id)
elif (len(args) == 9 and args[:8] == ["exec", container_id, "curl",
      "--connect-timeout", "2", "--max-time", "5", "-fsS"]
      and args[8] in ("http://127.0.0.1:8080/healthz", "http://127.0.0.1:8080/",
                      "http://127.0.0.1:8080/api/security/status")):
    if not state["started"]:
        reject("exec before successful start")
    if args[8].endswith("/healthz"):
        state["health_calls"] += 1
        save()
        if failure == "health" or state["health_calls"] <= config.get("health_failures", 0):
            sys.exit(22)
        print("ok")
    elif args[8].endswith("/api/security/status"):
        fail("security_status")
        print('{"security_key_required":' + ('false' if failure == "security_status_content" else 'true') + '}')
    else:
        fail("page")
        print("Unexpected page" if failure == "page_content" else "<html>Security Key Required</html>")
elif len(args) == 5 and args[:4] == ["exec", container_id, "sh", "-lc"]:
    if not state["started"]:
        reject("exec before successful start")
    script = args[4]
    if script not in config["security_scripts"]:
        reject("unexpected security verification script")
    phase = config["security_scripts"][script]
    fail(phase)
elif args == ["logs", container_id]:
    if state["created"] != container_id:
        reject("logs for a container not created by this invocation")
    print("fake retained container logs")
elif args == ["ps", "--filter", "id=" + container_id]:
    if state["created"] != container_id:
        reject("status for a container not created by this invocation")
    fail("status")
    print(container_id + " Up")
elif args == ["image", "inspect", base_image, "--format", "{{.Id}}"]:
    fail("inspect")
    state["tag_image_id"] = "sha256:" + "c3" * 32
    save()
    print(config.get("returned_iid", config["image_id"]))
elif args == ["image", "inspect", config["image_id"], "--format", '{{join .RepoDigests "\\n"}}']:
    fail("digest")
    print(base_image + "@sha256:" + "b" * 64)
elif (len(args) == 5 and args[:4] == ["run", config["image_id"], "sh", "-lc"]
      and "Linux image smoke test: OK" in args[4]):
    state["smoke_created"] = True
    save()
    fail("smoke")
    print("Linux image smoke test: OK")
else:
    reject("unrecognized Docker command or arguments")
'''

SECURITY_SCRIPTS = {
    '\n  set -eu\n  headers="$(curl --connect-timeout 2 --max-time 5 -fsSI http://127.0.0.1:8080/)"\n  printf "%s\\n" "$headers" | tr -d "\\r" | grep -qi "^X-Frame-Options: DENY$"\n': "headers",
    '\n  set -eu\n  code="$(curl --connect-timeout 2 --max-time 5 -sS -o /tmp/no-bootstrap.json -w "%{http_code}" -X POST -H "Content-Type: application/json" -d "{}" http://127.0.0.1:8080/api/security/register/options)"\n  test "$code" = "403"\n': "bootstrap_denied",
    '\n  set -eu\n  token="$(cat "$WEBAUTHN_BOOTSTRAP_TOKEN_FILE")"\n  code="$(curl --connect-timeout 2 --max-time 5 -sS -o /tmp/bootstrap-options.json -w "%{http_code}" -X POST -H "Content-Type: application/json" -H "X-Bootstrap-Token: $token" -d "{}" http://127.0.0.1:8080/api/security/register/options)"\n  test "$code" = "200"\n  grep -q "\\\"challenge\\\"" /tmp/bootstrap-options.json\n': "bootstrap_allowed",
}


class ContainerScriptTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(BASH, "bash is needed to run the shell scripts")
        self.assertIsNotNone(GREP, "grep is needed to run the shell scripts")
        self.tmp = tempfile.TemporaryDirectory(prefix="container-script-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        for utility in ("grep", "basename", "dirname", "cat", "mktemp", "rm", "rmdir", "tr"):
            source = shutil.which(utility)
            self.assertIsNotNone(source, utility + " is needed to run the shell scripts")
            (self.bin / utility).symlink_to(source)
        self.secrets = {}
        for variable in ("SESSION_SECRET_FILE", "WEBAUTHN_BOOTSTRAP_TOKEN_FILE", "DATA_ENCRYPTION_KEY_FILE"):
            path = self.directory / variable.lower()
            path.write_text("dummy-test-secret-never-a-real-credential")
            self.secrets[variable] = str(path)
        self.build_tmp = self.directory / "build-tmp"
        self.build_tmp.mkdir()
        docker = self.bin / "docker"
        docker.write_text("#!" + sys.executable + "\n" + FAKE_DOCKER)
        docker.chmod(0o755)
        sleep = self.bin / "sleep"
        sleep.write_text("#!" + sys.executable + "\nimport sys\nsys.exit(0)\n")
        sleep.chmod(0o755)

    def run_script(self, script="deploy-container-server.sh", *, failure=None,
                   cleanup=None, existing=(), health_failures=0, env=None, returned_iid=None, returned_container_id=None):
        overrides = {
            **self.secrets, "WEBAUTHN_RP_ID": "localhost",
            "WEBAUTHN_ORIGIN": "http://localhost:8080", **dict(env or {}),
        }
        config = {
            "id": CONTAINER_ID,
            "name": overrides.get("CONTAINER_NAME", "codex-linux-server"),
            "port": overrides.get("HOST_PORT", "8080"),
            "base_image": overrides.get("LINUX_IMAGE", "ubuntu:latest"),
            "server_image": overrides.get("SERVER_IMAGE", "codex-linux-server:latest"),
            "image_id": IMAGE_ID,
            "volume": overrides.get("DATA_VOLUME", "codex-security-data"),
            "failure": failure,
            "health_failures": health_failures,
        }
        if returned_iid is not None:
            config["returned_iid"] = returned_iid
        if returned_container_id is not None:
            config["returned_container_id"] = returned_container_id
        config["create_args"] = [
            "create", "--name", config["name"], "--restart", "unless-stopped",
            "-p", "127.0.0.1:" + config["port"] + ":8080",
            "-v", config["volume"] + ":/data",
        ]
        for variable, destination in (
            ("SESSION_SECRET_FILE", "session_secret"),
            ("WEBAUTHN_BOOTSTRAP_TOKEN_FILE", "webauthn_bootstrap_token"),
            ("DATA_ENCRYPTION_KEY_FILE", "data_encryption_key"),
        ):
            config["create_args"] += ["--mount", "type=bind,src=" + str(Path(overrides[variable]).resolve())
                                      + ",dst=/run/secrets/" + destination + ",readonly"]
        config["create_args"] += [
            "-e", "SESSION_SECRET_FILE=/run/secrets/session_secret",
            "-e", "WEBAUTHN_BOOTSTRAP_TOKEN_FILE=/run/secrets/webauthn_bootstrap_token",
            "-e", "DATA_ENCRYPTION_KEY_FILE=/run/secrets/data_encryption_key",
            "-e", "WEBAUTHN_RP_ID=" + overrides["WEBAUTHN_RP_ID"],
            "-e", "WEBAUTHN_ORIGIN=" + overrides["WEBAUTHN_ORIGIN"],
            "-e", "WEBAUTHN_RP_NAME=" + overrides.get("WEBAUTHN_RP_NAME", "Codex Container Server"),
            IMAGE_ID,
        ]
        config["security_scripts"] = SECURITY_SCRIPTS
        self.config = config
        state = {
            "existing": list(existing), "created": None, "started": False,
            "health_calls": 0, "race_seen": False, "smoke_created": False,
            "built": None, "volume_created": False,
        }
        paths = {
            "CONFIG": self.directory / "config.json",
            "STATE": self.directory / "state.json",
            "LOG": self.directory / "commands.jsonl",
            "REJECTIONS": self.directory / "rejections.txt",
        }
        paths["CONFIG"].write_text(json.dumps(config))
        paths["STATE"].write_text(json.dumps(state))
        paths["LOG"].write_text("")
        paths["REJECTIONS"].write_text("")
        # Do not inherit Docker configuration or script options from the host.
        process_env = {
            "PATH": str(self.bin), "HOME": str(self.directory), "LC_ALL": "C",
            "TMPDIR": str(self.build_tmp),
            **{"FAKE_DOCKER_" + key: str(value) for key, value in paths.items()},
            **overrides,
        }
        if cleanup is not None:
            process_env["CLEANUP_AFTER_TEST"] = cleanup
        result = subprocess.run(
            [BASH, str(ROOT / "scripts" / script)], cwd=ROOT,
            env=process_env, text=True, capture_output=True, timeout=10,
        )
        self.commands = [json.loads(line) for line in paths["LOG"].read_text().splitlines()]
        self.state = json.loads(paths["STATE"].read_text())
        self.assertEqual(paths["REJECTIONS"].read_text(), "", result.stdout + result.stderr)
        self.assert_safe_commands()
        self.assertEqual(list(self.build_tmp.iterdir()), [], "Temporary image IDs must be cleaned up")
        return result

    def assert_safe_commands(self):
        for command in self.commands:
            self.assertNotIn(command[0], {"rm", "rmi", "stop", "restart", "kill", "prune"})
            self.assertFalse(any(arg == "--rm" or arg.startswith("--rm=") for arg in command))
            if command[0] in {"start", "exec", "logs"}:
                self.assertEqual(command[1], CONTAINER_ID, "Lifecycle operations must use the captured ID")
            if command[0] == "ps" and "--filter" in command:
                self.assertEqual(command[command.index("--filter") + 1], "id=" + CONTAINER_ID)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_failure(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_success_retains_created_container_and_pins_operations_to_id(self):
        result = self.run_script()
        self.assert_success(result)
        self.assertEqual([command[0] for command in self.commands],
                         ["ps", "pull", "build", "volume", "create", "start"] + ["exec"] * 6 + ["ps"])
        self.assertEqual(self.state["created"], CONTAINER_ID)
        self.assertTrue(self.state["started"])
        self.assertIn(CONTAINER_ID, result.stdout + result.stderr)
        self.assertIn("http://127.0.0.1:8080", result.stdout)

    def test_legacy_true_cleanup_is_ignored_on_success(self):
        result = self.run_script(cleanup="true")
        self.assert_success(result)
        self.assertEqual(self.state["created"], CONTAINER_ID)
        self.assertIn("CLEANUP_AFTER_TEST", result.stdout + result.stderr)

    def test_existing_running_or_stopped_container_is_untouched(self):
        for status in ("running", "stopped"):
            for cleanup in (None, "true"):
                with self.subTest(status=status, cleanup=cleanup):
                    existing = [{"name": "codex-linux-server", "status": status}]
                    result = self.run_script(existing=existing, cleanup=cleanup)
                    self.assert_failure(result)
                    self.assertEqual(self.commands, [["ps", "-a", "--format", "{{.Names}}"]])
                    self.assertEqual(self.state["existing"], existing)
                    self.assertIsNone(self.state["created"])

    def test_preflight_matches_exact_names_not_prefixes_or_suffixes(self):
        existing = [{"name": name, "status": "running"} for name in
                    ("codex-linux-server-old", "old-codex-linux-server", "codex-linux")]
        result = self.run_script(existing=existing)
        self.assert_success(result)
        self.assertEqual(self.state["existing"], existing)

    def test_precreation_failures_never_create_or_touch_existing_containers(self):
        expected = {
            "preflight": ["ps"],
            "pull": ["ps", "pull"],
            "build": ["ps", "pull", "build"],
            "volume": ["ps", "pull", "build", "volume"],
            "create": ["ps", "pull", "build", "volume", "create"],
        }
        for phase, operations in expected.items():
            for cleanup in (None, "true"):
                with self.subTest(phase=phase, cleanup=cleanup):
                    result = self.run_script(failure=phase, cleanup=cleanup)
                    self.assert_failure(result)
                    self.assertEqual([command[0] for command in self.commands], operations)
                    self.assertIsNone(self.state["created"])
                    self.assertFalse(self.state["started"])

    def test_name_collision_after_preflight_does_not_start_racing_container(self):
        for cleanup in (None, "true"):
            with self.subTest(cleanup=cleanup):
                result = self.run_script(failure="race", cleanup=cleanup)
                self.assert_failure(result)
                self.assertTrue(self.state["race_seen"])
                self.assertIsNone(self.state["created"])
                self.assertEqual([command[0] for command in self.commands],
                                 ["ps", "pull", "build", "volume", "create"])
                self.assertEqual(self.state["existing"],
                                 [{"name": "codex-linux-server", "status": "running"}])

    def test_postcreation_failures_retain_container_even_with_legacy_cleanup(self):
        for phase in ("start", "health", "page", "page_content", "security_status",
                      "security_status_content", "headers", "bootstrap_denied", "bootstrap_allowed", "status"):
            for cleanup in (None, "true"):
                with self.subTest(phase=phase, cleanup=cleanup):
                    result = self.run_script(failure=phase, cleanup=cleanup)
                    self.assert_failure(result)
                    self.assertEqual(self.state["created"], CONTAINER_ID)
                    self.assertIn(CONTAINER_ID, result.stdout + result.stderr)
                    self.assertEqual(self.state["started"], phase != "start")
                    if phase == "health":
                        self.assertEqual(self.state["health_calls"], 45)
                        self.assertIn(["logs", CONTAINER_ID], self.commands)
                        self.assertFalse(any(command[-1] == "http://127.0.0.1:8080/"
                                             for command in self.commands))
                    elif phase == "start":
                        self.assertFalse(any(command[0] == "exec" for command in self.commands))

    def test_transient_health_failures_retry_and_succeed(self):
        result = self.run_script(health_failures=2)
        self.assert_success(result)
        self.assertEqual(self.state["health_calls"], 3)

    def test_nondefault_name_port_and_images_are_preserved(self):
        result = self.run_script(env={
            "CONTAINER_NAME": "retained.server-2", "HOST_PORT": "18080",
            "LINUX_IMAGE": "ubuntu:24.04", "SERVER_IMAGE": "example/server:manual",
            "DATA_VOLUME": "isolated-test-data", "WEBAUTHN_RP_ID": "example.test",
            "WEBAUTHN_ORIGIN": "https://example.test", "WEBAUTHN_RP_NAME": "Test RP",
        })
        self.assert_success(result)
        self.assertIn(self.config["create_args"], self.commands)
        self.assertIn("http://127.0.0.1:18080", result.stdout)

    def test_invalid_container_names_fail_before_any_docker_operation(self):
        for name in ("-leading", "has space", "path/name", "line\nbreak"):
            with self.subTest(name=name):
                result = self.run_script(env={"CONTAINER_NAME": name}, cleanup="true")
                self.assert_failure(result)
                self.assertEqual(self.commands, [])

    def test_invalid_ports_fail_before_any_docker_operation(self):
        for port in ("0", "65536", "abc", "8080:9000", "-1", "1.5"):
            with self.subTest(port=port):
                result = self.run_script(env={"HOST_PORT": port}, cleanup="true")
                self.assert_failure(result)
                self.assertEqual(self.commands, [])


    def test_invalid_or_missing_build_image_id_fails_closed(self):
        for value in ("", "ubuntu:latest", "sha256:short", "sha256:" + "G" * 64,
                      IMAGE_ID + "\n" + IMAGE_ID):
            with self.subTest(value=value):
                result = self.run_script(returned_iid=value)
                self.assert_failure(result)
                self.assertEqual([command[0] for command in self.commands], ["ps", "pull", "build"])
                self.assertIsNone(self.state["created"])
        result = self.run_script(failure="missing_iid")
        self.assert_failure(result)
        self.assertEqual([command[0] for command in self.commands], ["ps", "pull", "build"])

    def test_image_tag_race_cannot_change_created_image(self):
        result = self.run_script()
        self.assert_success(result)
        create = next(command for command in self.commands if command[0] == "create")
        self.assertEqual(create[-1], IMAGE_ID)
        self.assertNotEqual(create[-1], self.state["tag_image_id"])
        self.assertNotIn(self.config["server_image"], create)
        self.assertIn(self.config["create_args"], self.commands)
        self.assertNotIn("dummy-test-secret-never-a-real-credential", json.dumps(self.commands))
        self.assertNotIn("dummy-test-secret-never-a-real-credential", result.stdout + result.stderr)

    def test_invalid_returned_container_id_never_starts_or_executes(self):
        for value in ("", "codex-linux-server", "abc", "A" * 64, CONTAINER_ID + "\nother"):
            with self.subTest(value=value):
                result = self.run_script(returned_container_id=value)
                self.assert_failure(result)
                self.assertEqual([command[0] for command in self.commands],
                                 ["ps", "pull", "build", "volume", "create"])
                self.assertFalse(self.state["started"])

    def test_missing_or_empty_secrets_fail_before_docker(self):
        for variable in self.secrets:
            for empty in (False, True):
                with self.subTest(variable=variable, empty=empty):
                    path = self.directory / ("empty" if empty else "missing")
                    if empty:
                        path.write_text("")
                    result = self.run_script(env={variable: str(path)})
                    self.assert_failure(result)
                    self.assertEqual(self.commands, [])

    def test_required_webauthn_configuration_fails_closed(self):
        for variable in ("WEBAUTHN_RP_ID", "WEBAUTHN_ORIGIN"):
            with self.subTest(variable=variable):
                result = self.run_script(env={variable: ""})
                self.assert_failure(result)
                self.assertEqual(self.commands, [])

    def test_every_http_check_has_connect_and_total_timeouts(self):
        result = self.run_script()
        self.assert_success(result)
        checks = [command for command in self.commands if command[0] == "exec"]
        self.assertEqual(len(checks), 6)
        for command in checks:
            if command[2] == "curl":
                self.assertEqual(command[3:7], ["--connect-timeout", "2", "--max-time", "5"])
            else:
                self.assertEqual(command[2:4], ["sh", "-lc"])
                self.assertEqual(command[4].count("curl "), 1)
                self.assertIn("curl --connect-timeout 2 --max-time 5 ", command[4])

    def test_header_check_propagates_curl_failure_after_matching_output(self):
        result = self.run_script()
        self.assert_success(result)
        script = next(command[4] for command in self.commands
                      if command[:4] == ["exec", CONTAINER_ID, "sh", "-lc"]
                      and "X-Frame-Options" in command[4])
        shell = shutil.which("sh")
        self.assertIsNotNone(shell)
        curl = self.bin / "curl"
        for exit_code in (0, 28):
            with self.subTest(exit_code=exit_code):
                curl.write_text("#!" + sys.executable + "\nimport sys\n"
                                "print('X-Frame-Options: DENY\\r')\n"
                                "sys.exit(" + str(exit_code) + ")\n")
                curl.chmod(0o755)
                # Execute the captured container-shell payload, with no network.
                checked = subprocess.run([shell, "-c", script],
                                         env={"PATH": str(self.bin), "LC_ALL": "C"},
                                         text=True, capture_output=True, timeout=5)
                self.assertEqual(checked.returncode, exit_code, checked.stderr)

    def test_smoke_invalid_image_id_fails_before_run(self):
        for value in ("", "ubuntu:latest", "sha256:short", "sha256:" + "G" * 64):
            with self.subTest(value=value):
                result = self.run_script("run-latest-linux.sh", returned_iid=value)
                self.assert_failure(result)
                self.assertEqual([command[0] for command in self.commands], ["pull", "image"])
                self.assertFalse(self.state["smoke_created"])

    def test_smoke_run_pins_id_even_when_tag_moves(self):
        result = self.run_script("run-latest-linux.sh")
        self.assert_success(result)
        run = next(command for command in self.commands if command[0] == "run")
        self.assertEqual(run[1], IMAGE_ID)
        self.assertNotEqual(run[1], self.state["tag_image_id"])

    def test_smoke_success_retains_container_without_auto_remove(self):
        result = self.run_script("run-latest-linux.sh")
        self.assert_success(result)
        self.assertEqual([command[0] for command in self.commands], ["pull", "image", "image", "run"])
        self.assertTrue(self.state["smoke_created"])
        self.assertRegex(result.stdout + result.stderr, r"(?i)retain|preserv")

    def test_smoke_failures_never_remove_container(self):
        expected = {"pull": ["pull"], "inspect": ["pull", "image"],
                    "digest": ["pull", "image", "image"],
                    "smoke": ["pull", "image", "image", "run"]}
        for phase, operations in expected.items():
            with self.subTest(phase=phase):
                result = self.run_script("run-latest-linux.sh", failure=phase, cleanup="true")
                self.assert_failure(result)
                self.assertEqual([command[0] for command in self.commands], operations)
                self.assertEqual(self.state["smoke_created"], phase == "smoke")


if __name__ == "__main__":
    unittest.main()

