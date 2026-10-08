"""Strict, testable loading for environment or file-backed application secrets.

Set *exactly one* of VALUE or VALUE_FILE for each secret. Never silently
prefer either source, and never include secret contents in diagnostics.
"""
import os
from pathlib import Path
from typing import Mapping


def require_secret(
    name: str, file_name: str, *, environ: Mapping[str, str] | None = None
) -> str:
    source = os.environ if environ is None else environ
    direct = (source.get(name) or "").strip()
    file_path = (source.get(file_name) or "").strip()

    if direct and file_path:
        raise RuntimeError(
            f"configure only one of {name} or {file_name}; unset the unused variable"
        )

    if file_path:
        try:
            value = Path(file_path).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(f"unable to read {file_name}") from exc
        if not value:
            raise RuntimeError(f"{file_name} points to an empty secret")
        return value

    if direct:
        return direct

    raise RuntimeError(f"{name} or {file_name} must be configured")
