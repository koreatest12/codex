#!/usr/bin/env python3
"""Generate a local administrator account without exposing its password to Git."""
import argparse
import json
import os
import secrets
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "app"))
from admin_auth import make_account  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a password-protected local admin identity")
    parser.add_argument("--username", default="admin", help="administrator login name (default: admin)")
    parser.add_argument("--rotate", action="store_true", help="replace an existing account hash")
    args = parser.parse_args()

    # Terminal-only output: never print a reusable password to CI or redirected logs.
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("run interactively in a local terminal; passwords cannot appear in CI logs")
    secrets_dir = REPO / "secrets"
    target = secrets_dir / "admin_account"
    if target.exists() and not args.rotate:
        parser.error("account file already exists; use --rotate for an intentional replacement")
    if not secrets_dir.is_dir():
        parser.error("run scripts/generate-security-env.sh first to create the secrets directory")

    password = secrets.token_urlsafe(36)
    account = make_account(args.username, password)
    os.umask(0o077)
    temporary = secrets_dir / (".admin_account." + secrets.token_hex(8))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(temporary, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(account, stream, separators=(",", ":"))
            stream.write("\n")
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()

    print("\n=== Save these once to your password manager ===")
    print("Account:", args.username)
    print("Password:", password)
    print("Stored file:", target)
    print("Only a salted scrypt password hash is stored in that file.")
    print("Never upload this output or the secrets directory to GitHub.")
    print("After rotation, recreate the container and rotate the session secret.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
