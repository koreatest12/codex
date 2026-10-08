#!/usr/bin/env python3
"""Check configured secret sources without ever displaying their values."""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from secret_config import require_secret  # noqa: E402

PAIRS = (
    ("SESSION_SECRET", "SESSION_SECRET_FILE"),
    ("WEBAUTHN_BOOTSTRAP_TOKEN", "WEBAUTHN_BOOTSTRAP_TOKEN_FILE"),
    ("DATA_ENCRYPTION_KEY", "DATA_ENCRYPTION_KEY_FILE"),
)


def main():
    parser = argparse.ArgumentParser(
        description="Check application secret sources without exposing secret values"
    )
    parser.add_argument(
        "--mode", choices=["auto", "file", "direct"], default="auto",
        help="Require file or direct secret sources, or accept either (auto)",
    )
    args = parser.parse_args()
    failures = 0

    for name, file_name in PAIRS:
        is_direct = bool(os.environ.get(name, "").strip())
        is_file = bool(os.environ.get(file_name, "").strip())
        try:
            if args.mode == "file" and (is_direct or not is_file):
                raise RuntimeError(f"{name}: expected FILE-only configuration")
            if args.mode == "direct" and (is_file or not is_direct):
                raise RuntimeError(f"{name}: expected direct-only configuration")
            require_secret(name, file_name)
        except RuntimeError as exc:
            # Do not log secret values or arbitrary file paths.
            print(f"FAIL {name}: {exc}", file=sys.stderr)
            failures += 1
        else:
            print(f"OK {name}: {'file' if is_file else 'direct'} source validated")

    if failures:
        print(f"Configuration check failed: {failures} secret source(s)", file=sys.stderr)
        return 1
    print("Secret source preflight: PASS (values redacted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
