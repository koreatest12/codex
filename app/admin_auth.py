"""Single local administrator account. Passwords are scrypt hashed, never stored."""
import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,31}$")
SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1


def make_account(username: str, password: str) -> dict:
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("username must contain 3-32 ASCII letters, digits, _ . or -")
    if not isinstance(password, str) or len(password) < 16 or len(password) > 512:
        raise ValueError("password must be 16-512 characters")
    salt = secrets.token_bytes(32)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
        maxmem=64 * 1024 * 1024,
    )
    return {
        "version": 1,
        "username": username,
        "algorithm": "scrypt",
        "salt": base64.b64encode(salt).decode("ascii"),
        "password_hash": base64.b64encode(key).decode("ascii"),
    }


@dataclass(frozen=True)
class AdminAccount:
    username: str
    salt: bytes
    password_hash: bytes
    fingerprint: str

    @classmethod
    def from_file(cls, source: str):
        path = Path(source)
        # No directory traversal or default fallbacks: an invalid configured file fails startup.
        raw = path.read_bytes()
        if not raw or len(raw) > 4096:
            raise ValueError("invalid account file size")
        data = json.loads(raw)
        if (not isinstance(data, dict) or data.get("version") != 1
                or data.get("algorithm") != "scrypt"
                or not isinstance(data.get("username"), str)
                or not USERNAME_PATTERN.fullmatch(data["username"])):
            raise ValueError("unsupported admin account format")
        salt = base64.b64decode(data["salt"], validate=True)
        key = base64.b64decode(data["password_hash"], validate=True)
        if len(salt) != 32 or len(key) != 32:
            raise ValueError("invalid administrator credential digest")
        return cls(
            username=data["username"],
            salt=salt,
            password_hash=key,
            fingerprint=hashlib.sha256(raw).hexdigest(),
        )

    def verify(self, username: str, password: str) -> bool:
        if not isinstance(username, str) or not isinstance(password, str):
            return False
        if len(username) > 128 or len(password) > 512:
            return False
        key = hashlib.scrypt(
            password.encode("utf-8"),
            salt=self.salt,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=32,
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(username.encode(), self.username.encode()) and hmac.compare_digest(
            key, self.password_hash
        )
