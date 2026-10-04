"""Container-retention regression tests. No Docker daemon or network is used.

Run from the repository root with:
    python3 -m unittest discover -s tests -v

Every script runs with a restricted PATH containing only a strict Docker fake,
a no-op sleep, and grep. Unknown Docker operations fail the test, even when the
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
elif args == ["build", "--pull", "--build-arg", "BASE_IMAGE=" + base_image,
              "-t", server_image, "."]:
    fail("build")
    print("fake image built")
elif args == ["create", "--name", name, "--restart", "unless-stopped", "-p",
              "127.0.0.1:" + config["port"] + ":8080", server_image]:
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
    print(container_id)
elif args == ["start", container_id]:
    if state["created"] != container_id:
        reject("start before creation")
    fail("start")
    state["started"] = True
    save()
    print(container_id)
elif (len(args) == 5 and args[:4] == ["exec", container_id, "curl", "-fsS"]
      and args[4] in ("http://127.0.0.1:8080/healthz", "http://127.0.0.1:8080/")):
    if not state["started"]:
        reject("exec before successful start")
    if args[4].endswith("/healthz"):
        state["health_calls"] += 1
        save()
        if failure == "health" or state["health_calls"] <= config.get("health_failures", 0):
            print("simulated health failure", file=sys.stderr)
            sys.exit(22)
        print("ok")
    else:
        fail("page")
        if failure == "page_content":
            print("Unexpected page")
        else:
            print("<html>Codex Linux Container Server</html>")
elif args == ["logs", container_id]:
    if state["created"] != container_id:
        reject("logs for a container not created by this invocation")
    print("fake retained container logs")
elif args == ["ps", "--filter", "id=" + container_id]:
    if state["created"] != container_id:
        reject("status for a container not created by this invocation")
    fail("status")
    print(container_id + " Up")
elif args == ["image", "inspect", base_image, "--format", '{{join .RepoDigests "\\n"}}']:
    fail("inspect")
    print(base_image + "@sha256:" + "b" * 64)
elif (len(args) == 5 and args[:4] == ["run", base_image, "sh", "-lc"]
      and "Linux image smoke test: OK" in args[4]):
    state["smoke_created"] = True
    save()
    fail("smoke")
    print("Linux image smoke test: OK")
else:
    reject("unrecognized Docker command or arguments")
'''


class ContainerScriptTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(BASH, "bash is needed to run the shell scripts")
        self.assertIsNotNone(GREP, "grep is needed to run the shell scripts")
        self.tmp = tempfile.TemporaryDirectory(prefix="container-script-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.bin = self.directory / "bin"
        self.bin.mkdir()
        (self.bin / "grep").symlink_to(GREP)
        docker = self.bin / "docker"
        docker.write_text("#!" + sys.executable + "\n" + FAKE_DOCKER)
        docker.chmod(0o755)
        sleep = self.bin / "sleep"
        sleep.write_text("#!" + sys.executable + "\nimport sys\nsys.exit(0)\n")
        sleep.chmod(0o755)

    def run_script(self, script="deploy-container-server.sh", *, failure=None,
                   cleanup=None, existing=(), health_failures=0, env=None):
        overrides = dict(env or {})
        config = {
            "id": CONTAINER_ID,
            "name": overrides.get("CONTAINER_NAME", "codex-linux-server"),
            "port": overrides.get("HOST_PORT", "8080"),
            "base_image": overrides.get("LINUX_IMAGE", "ubuntu:latest"),
            "server_image": overrides.get("SERVER_IMAGE", "codex-linux-server:latest"),
            "failure": failure,
            "health_failures": health_failures,
        }
        state = {
            "existing": list(existing), "created": None, "started": False,
            "health_calls": 0, "race_seen": False, "smoke_created": False,
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
                         ["ps", "pull", "build", "create", "start", "exec", "exec", "ps"])
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
            "create": ["ps", "pull", "build", "create"],
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
                                 ["ps", "pull", "build", "create"])
                self.assertEqual(self.state["existing"],
                                 [{"name": "codex-linux-server", "status": "running"}])

    def test_postcreation_failures_retain_container_even_with_legacy_cleanup(self):
        for phase in ("start", "health", "page", "page_content", "status"):
            for cleanup in (None, "true"):
                with self.subTest(phase=phase, cleanup=cleanup):
                    result = self.run_script(failure=phase, cleanup=cleanup)
                    self.assert_failure(result)
                    self.assertEqual(self.state["created"], CONTAINER_ID)
                    self.assertIn(CONTAINER_ID, result.stdout + result.stderr)
                    self.assertEqual(self.state["started"], phase != "start")
                    if phase == "health":
                        self.assertEqual(self.state["health_calls"], 30)
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
        })
        self.assert_success(result)
        self.assertIn(["create", "--name", "retained.server-2", "--restart", "unless-stopped",
                       "-p", "127.0.0.1:18080:8080", "example/server:manual"], self.commands)
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

    def test_smoke_success_retains_container_without_auto_remove(self):
        result = self.run_script("run-latest-linux.sh")
        self.assert_success(result)
        self.assertEqual([command[0] for command in self.commands], ["pull", "image", "run"])
        self.assertTrue(self.state["smoke_created"])
        self.assertRegex(result.stdout + result.stderr, r"(?i)retain|preserv")

    def test_smoke_failures_never_remove_container(self):
        expected = {"pull": ["pull"], "inspect": ["pull", "image"],
                    "smoke": ["pull", "image", "run"]}
        for phase, operations in expected.items():
            with self.subTest(phase=phase):
                result = self.run_script("run-latest-linux.sh", failure=phase, cleanup="true")
                self.assert_failure(result)
                self.assertEqual([command[0] for command in self.commands], operations)
                self.assertEqual(self.state["smoke_created"], phase == "smoke")


if __name__ == "__main__":
    unittest.main()
