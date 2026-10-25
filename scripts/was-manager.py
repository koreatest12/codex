#!/usr/bin/env python3
"""Host-only WAS lifecycle control for the existing Docker Compose stack.

No remote host access, Docker socket HTTP API, embedded secrets or destructive
volume operations. This CLI must run on the actual Docker host.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import uuid4


ROOT = Path(__file__).resolve().parent.parent
SECRET_NAMES = ("session_secret", "webauthn_bootstrap_token", "data_encryption_key")
VOLUME_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class WasError(Exception):
    pass


class WasManager:
    def __init__(self, root: Path = ROOT):
        self.root = root.resolve()

    def compose(self) -> list[str]:
        files = ["-f", "compose.yaml"]
        account = self.root / "secrets" / "admin_account"
        if account.exists():
            if not account.is_file() or not account.stat().st_size:
                raise WasError("Administrator credential file is empty or invalid.")
            files += ["-f", "compose.account.yaml"]
        return ["docker", "compose", *files]

    def run(self, args: list[str], *, capture: bool = False) -> str:
        try:
            result = subprocess.run(
                args,
                cwd=self.root,
                check=True,
                text=True,
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.PIPE if capture else None,
            )
        except FileNotFoundError as error:
            raise WasError(f"Required command is unavailable: {args[0]}") from error
        except subprocess.CalledProcessError as error:
            # Never echo a compose config dump, environment variable or log.
            raise WasError(f"Command failed (exit {error.returncode}): {args[0]} {args[1]}") from error
        return result.stdout.strip() if capture else ""

    def docker(self) -> None:
        self.run(["docker", "info"], capture=True)
        self.run(["docker", "compose", "version"], capture=True)

    def secrets(self) -> None:
        if (self.root / ".env").is_symlink():
            raise WasError(".env must not be a symlink.")
        if (self.root / "secrets").is_symlink():
            raise WasError("secrets/ must not be a symlink.")
        if not (self.root / ".env").is_file():
            raise WasError("Missing .env; on a fresh host run: init")
        for name in SECRET_NAMES:
            file = self.root / "secrets" / name
            if file.is_symlink() or not file.is_file() or file.stat().st_size == 0:
                raise WasError(f"Missing/invalid secret file: secrets/{name}")
        account = self.root / "secrets" / "admin_account"
        if account.is_symlink():
            raise WasError("Administrator secret must not be a symlink.")

    def config(self) -> dict:
        self.secrets()
        try:
            obj = json.loads(self.run([*self.compose(), "config", "--format", "json"], capture=True))
            if not isinstance(obj, dict) or "web" not in obj.get("services", {}):
                raise ValueError("missing web service")
            return obj
        except (ValueError, KeyError) as error:
            raise WasError("Docker Compose configuration is invalid.") from error

    def image(self, config: dict) -> str:
        name = config["services"]["web"].get("image")
        if not isinstance(name, str) or not name:
            raise WasError("Compose web service has no image.")
        self.run(["docker", "image", "inspect", name], capture=True)
        return name

    def volume(self, config: dict) -> str:
        try:
            name = config["volumes"]["security-data"]["name"]
        except (KeyError, TypeError) as error:
            raise WasError("Missing persistent security-data volume configuration.") from error
        if not isinstance(name, str) or not VOLUME_NAME.fullmatch(name):
            raise WasError("Invalid persistent volume identifier.")
        self.run(["docker", "volume", "inspect", name], capture=True)
        return name

    def doctor(self) -> None:
        print("WAS: Nginx -> Gunicorn -> Flask (WebAuthn-protected)")
        print("Host-only management; no public admin or Docker API exposed.")
        self.secrets()
        print("Local configuration and three secret files: present (values hidden)")
        self.docker()
        self.config()
        print("Docker Engine, Compose and configuration: OK")
        print("For a deployed instance: status / health. For a fresh install: deploy.")

    def init(self, rp_id: str, origin: str) -> None:
        secret_dir = self.root / "secrets"
        env_file = self.root / ".env"
        paths = (env_file, *(secret_dir / name for name in (*SECRET_NAMES, "admin_account")))
        if secret_dir.is_symlink() or any(p.exists() or p.is_symlink() for p in paths):
            raise WasError("Existing configuration or symlink found; refusing to overwrite secrets.")
        self.run(["bash", "scripts/generate-security-env.sh", rp_id, origin])
        print("Local secrets created. Register a real FIDO2 key in the browser after deployment.")

    def install_docker(self) -> None:
        if not hasattr(os, "geteuid") or os.geteuid() != 0:
            raise WasError("Ubuntu Docker installation requires: sudo python3 scripts/was-manager.py install-docker")
        self.run(["bash", "scripts/install-docker-ubuntu.sh"])

    def health(self, attempts: int = 1) -> None:
        self.docker()
        self.config()
        endpoint = self.run([*self.compose(), "port", "web", "8080"], capture=True)
        if not endpoint:
            raise WasError("No running WAS port is published.")
        port = endpoint.splitlines()[0].rsplit(":", 1)[-1]
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            raise WasError("Could not resolve the local published WAS port.")
        url = f"http://127.0.0.1:{port}/healthz"
        for index in range(attempts):
            try:
                with urlopen(url, timeout=4) as response:
                    if response.status == 200 and json.load(response).get("status") == "ok":
                        print(f"WAS healthy via Nginx -> Gunicorn -> Flask (local port {port})")
                        return
            except (HTTPError, URLError, ValueError, TimeoutError, OSError):
                pass
            if index + 1 < attempts:
                time.sleep(2)
        raise WasError("WAS failed the local /healthz probe. Check logs (no auto-recovery performed).")

    def deploy(self) -> None:
        self.docker()
        self.config()
        # Builds before recreating the service; it does not remove the data volume.
        self.run([*self.compose(), "build", "web"])
        self.run([*self.compose(), "up", "-d", "--no-build", "web"])
        self.health(attempts=20)
        print("Local WAS deploy verified; remote DNS/TLS and hardware-key login require host setup.")

    def start(self) -> None:
        self.docker()
        config = self.config()
        self.image(config)
        self.run([*self.compose(), "up", "-d", "--no-build", "web"])
        self.health(attempts=20)

    def stop(self) -> None:
        self.docker()
        self.config()
        self.run([*self.compose(), "stop", "web"])
        print("WAS stopped. Containers and persistent security-data volume retained.")

    def restart(self) -> None:
        self.docker()
        self.config()
        self.run([*self.compose(), "restart", "web"])
        self.health(attempts=20)

    def status(self) -> None:
        self.docker()
        self.config()
        self.run(["bash", "scripts/final-status.sh"])

    def logs(self, follow: bool, tail: int) -> None:
        self.docker()
        self.config()
        print("Warning: application logs may include private request metadata. Do not post raw logs publicly.")
        self.run([*self.compose(), "logs", "--tail", str(tail), *(["--follow"] if follow else []), "web"])

    def backup(self) -> Path:
        self.docker()
        config = self.config()
        image = self.image(config)  # Reuse a local image; never pull a random image during backup.
        volume = self.volume(config)
        cid = self.run([*self.compose(), "ps", "-q", "web"], capture=True)
        running = bool(cid and self.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", cid.splitlines()[0]],
            capture=True,
        ) == "true")
        destination = self.root / "backups"
        if destination.is_symlink():
            raise WasError("Backup directory must not be a symlink.")
        destination.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination.chmod(0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"codex-data-{stamp}-{uuid4().hex[:8]}.tar.gz"
        pending = destination / f".{filename}.partial"
        finished = destination / filename
        if pending.exists() or finished.exists():
            raise WasError("Refusing to overwrite an existing backup.")
        stopped = False
        error = None
        try:
            if running:
                self.run([*self.compose(), "stop", "web"])
                stopped = True
            self.run([
                "docker", "run", "--rm", "--network", "none", "--read-only",
                "--mount", f"type=volume,source={volume},target=/data,readonly",
                "--mount", f"type=bind,source={destination},target=/backup",
                "--entrypoint", "/bin/sh", image,
                "-eu", "-c", 'umask 077; tar -czf "/backup/$1" -C /data .',
                "_", pending.name,
            ])
            if not pending.is_file() or pending.stat().st_size <= 0:
                raise WasError("Backup archive is missing or empty.")
            pending.chmod(0o600)
            pending.replace(finished)
        except Exception as exc:
            error = exc
            pending.unlink(missing_ok=True)
        finally:
            if stopped:
                try:
                    self.run([*self.compose(), "start", "web"])
                except Exception as restart_error:
                    raise WasError("Backup finished/failed, but WAS could not restart; inspect status.") from restart_error
        if error is not None:
            raise error
        print(f"Backup created: {finished} (contains sensitive database; encrypt before off-host storage)")
        print("Keep the original data-encryption key and other secrets separately; never commit them.")
        return finished

    def upgrade(self) -> None:
        backup = self.backup()
        print(f"Pre-upgrade snapshot: {backup.name}")
        self.deploy()
        print("Upgrade completed. For rollback, use a reviewed old image and keep the same data volume.")


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="Manage the existing local Nginx/Gunicorn/Flask WebAuthn WAS without exposing Docker remotely."
    )
    commands = cli.add_subparsers(dest="command", required=True)
    for name in ("doctor", "install-docker", "start", "deploy", "stop",
                 "restart", "status", "health", "backup", "upgrade"):
        commands.add_parser(name)
    init = commands.add_parser("init", help="Create fresh local secrets once (never overwrite).")
    init.add_argument("--rp-id", default="localhost")
    init.add_argument("--origin", default="http://localhost:8080")
    logs = commands.add_parser("logs")
    logs.add_argument("--follow", action="store_true")
    logs.add_argument("--tail", type=int, default=100)
    return cli


def main() -> int:
    args = parser().parse_args()
    manager = WasManager()
    try:
        if args.command == "init":
            manager.init(args.rp_id, args.origin)
        elif args.command == "install-docker":
            manager.install_docker()
        elif args.command == "logs":
            if not 1 <= args.tail <= 5000:
                raise WasError("--tail must be between 1 and 5000.")
            manager.logs(args.follow, args.tail)
        else:
            getattr(manager, args.command)()
    except (WasError, OSError) as exc:
        print(f"WAS ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
