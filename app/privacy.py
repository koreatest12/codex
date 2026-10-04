import base64
import json
import os
from typing import Final

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ALLOWED_KINDS: Final[set[str]] = {
    "reservation",
    "phone",
    "email",
    "contact",
    "other",
}


def decode_data_key(encoded: str) -> bytes:
    value = encoded.strip().encode("ascii")
    padding = b"=" * ((4 - (len(value) % 4)) % 4)
    try:
        raw = base64.urlsafe_b64decode(value + padding)
    except Exception as exc:
        raise ValueError("data encryption key must be URL-safe base64") from exc
    if len(raw) != 32:
        raise ValueError("data encryption key must decode to exactly 32 bytes")
    return raw


def validate_kind(kind: str) -> str:
    normalized = (kind or "").strip().lower()
    if normalized not in ALLOWED_KINDS:
        raise ValueError("unsupported private-data kind")
    return normalized


def _mask_except_last(value: str, visible: int) -> str:
    if not value:
        return ""
    visible = max(0, min(visible, len(value)))
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]


def _mask_phone(value: str) -> str:
    digit_positions = [index for index, char in enumerate(value) if char.isdigit()]
    keep = set(digit_positions[-4:])
    return "".join(
        char if not char.isdigit() or index in keep else "*"
        for index, char in enumerate(value)
    )


def _mask_email(value: str) -> str:
    if "@" not in value:
        return _mask_except_last(value, 2)
    local, domain = value.rsplit("@", 1)
    masked_local = (local[:1] if local else "") + "***"
    parts = domain.split(".")
    host = parts[0] if parts else ""
    masked_host = (host[:1] if host else "") + "***"
    suffix = "." + ".".join(parts[1:]) if len(parts) > 1 else ""
    return f"{masked_local}@{masked_host}{suffix}"


def mask_value(kind: str, value: str) -> str:
    normalized = validate_kind(kind)
    text = value.strip()

    if normalized == "phone":
        return _mask_phone(text)
    if normalized == "email":
        return _mask_email(text)
    if normalized == "contact":
        if "@" in text:
            return _mask_email(text)
        if sum(char.isdigit() for char in text) >= 7:
            return _mask_phone(text)
        return _mask_except_last(text, 2)
    if normalized == "reservation":
        return _mask_except_last(text, 4)
    return _mask_except_last(text, 4)


class PrivacyCipher:
    """AES-256-GCM wrapper for private values stored in SQLite."""

    def __init__(self, encoded_key: str):
        self._aead = AESGCM(decode_data_key(encoded_key))

    @staticmethod
    def _aad(record_id: str, kind: str) -> bytes:
        return f"codex-private-value:v1:{record_id}:{validate_kind(kind)}".encode("utf-8")

    def encrypt(self, record_id: str, kind: str, label: str, value: str) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        plaintext = json.dumps(
            {"label": label, "value": value},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        ciphertext = self._aead.encrypt(nonce, plaintext, self._aad(record_id, kind))
        return nonce, ciphertext

    def decrypt(self, record_id: str, kind: str, nonce: bytes, ciphertext: bytes) -> dict[str, str]:
        plaintext = self._aead.decrypt(
            nonce,
            ciphertext,
            self._aad(record_id, kind),
        )
        payload = json.loads(plaintext.decode("utf-8"))
        label = payload.get("label")
        value = payload.get("value")
        if not isinstance(label, str) or not isinstance(value, str):
            raise ValueError("encrypted payload has an invalid shape")
        return {"label": label, "value": value}
