import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import shutil
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, render_template, request, session

from privacy import PrivacyCipher, mask_value, validate_kind
from admin_auth import AdminAccount
from data_manager import DataManager, DataManagerError, NotFound, RevisionConflict
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be configured")
    return value


def require_secret(name: str, file_name: str) -> str:
    direct = os.environ.get(name, "").strip()
    secret_file = os.environ.get(file_name, "").strip()

    if direct and secret_file:
        raise RuntimeError(f"configure only one of {name} or {file_name}")

    if secret_file:
        path = Path(secret_file)
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"unable to read {file_name}") from exc
        if not value:
            raise RuntimeError(f"{file_name} points to an empty secret")
        return value

    if direct:
        return direct

    raise RuntimeError(f"{name} or {file_name} must be configured")


SESSION_SECRET = require_secret("SESSION_SECRET", "SESSION_SECRET_FILE")
RP_ID = require_env("WEBAUTHN_RP_ID")
ORIGIN = require_env("WEBAUTHN_ORIGIN").rstrip("/")
BOOTSTRAP_TOKEN = require_secret(
    "WEBAUTHN_BOOTSTRAP_TOKEN", "WEBAUTHN_BOOTSTRAP_TOKEN_FILE"
)
DATA_ENCRYPTION_KEY = require_secret(
    "DATA_ENCRYPTION_KEY", "DATA_ENCRYPTION_KEY_FILE"
)
PRIVACY_CIPHER = PrivacyCipher(DATA_ENCRYPTION_KEY)
RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "Codex Container Server").strip()
USER_NAME = os.environ.get("WEBAUTHN_USER_NAME", "admin").strip()
DATABASE_PATH = Path(os.environ.get("WEBAUTHN_DB_PATH", "/data/webauthn.db"))
MANAGED_DATA_DB_PATH = Path(os.environ.get("MANAGED_DATA_DB_PATH", "/data/managed-data.db"))
DATA_MANAGER = DataManager(MANAGED_DATA_DB_PATH)
ADMIN_ACCOUNT_PATH = os.environ.get("ADMIN_ACCOUNT_FILE", "").strip()
ADMIN_ACCOUNT = AdminAccount.from_file(ADMIN_ACCOUNT_PATH) if ADMIN_ACCOUNT_PATH else None
STARTED_AT = time.monotonic()

origin = urlparse(ORIGIN)
if not origin.hostname:
    raise RuntimeError("WEBAUTHN_ORIGIN must be an absolute URL")

is_local_origin = origin.hostname in {"localhost", "127.0.0.1", "::1"}
if not is_local_origin and origin.scheme != "https":
    raise RuntimeError("HTTPS is required for non-localhost WebAuthn origins")

if RP_ID != "localhost" and not (
    origin.hostname == RP_ID or origin.hostname.endswith("." + RP_ID)
):
    raise RuntimeError("WEBAUTHN_RP_ID must match the origin host or its registrable suffix")

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = SESSION_SECRET
app.config.update(
    MAX_CONTENT_LENGTH=64 * 1024,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=origin.scheme == "https",
)


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def init_db() -> None:
    with db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS credentials (
                credential_key TEXT PRIMARY KEY,
                credential_id BLOB NOT NULL UNIQUE,
                public_key BLOB NOT NULL,
                sign_count INTEGER NOT NULL DEFAULT 0,
                transports TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_login_failures (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                count INTEGER NOT NULL,
                first_failed_at INTEGER NOT NULL,
                blocked_until INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS private_values (
                record_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                nonce BLOB NOT NULL,
                ciphertext BLOB NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def credential_rows():
    with db() as connection:
        return connection.execute(
            """
            SELECT credential_key, credential_id, public_key, sign_count, transports, created_at
            FROM credentials
            ORDER BY created_at
            """
        ).fetchall()


def credential_fingerprint(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def credential_count() -> int:
    with db() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM credentials").fetchone()
        return int(row["total"])


def private_value_count() -> int:
    with db() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM private_values").fetchone()
        return int(row["total"])


def private_value_rows():
    with db() as connection:
        return connection.execute(
            """
            SELECT record_id, kind, nonce, ciphertext, created_at, updated_at
            FROM private_values
            ORDER BY created_at DESC
            """
        ).fetchall()


def private_value_row(record_id: str):
    with db() as connection:
        return connection.execute(
            """
            SELECT record_id, kind, nonce, ciphertext, created_at, updated_at
            FROM private_values
            WHERE record_id = ?
            """,
            (record_id,),
        ).fetchone()


def require_authenticated():
    if not fully_authenticated():
        return jsonify({"error": "authentication required"}), 403
    return None


def get_or_create_user_id() -> bytes:
    with db() as connection:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'user_id'"
        ).fetchone()
        if row:
            return bytes(row["value"])

        user_id = secrets.token_bytes(32)
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('user_id', ?)",
            (sqlite3.Binary(user_id),),
        )
        return user_id


def bootstrap_authorized() -> bool:
    supplied = request.headers.get("X-Bootstrap-Token", "")
    return bool(supplied) and hmac.compare_digest(supplied, BOOTSTRAP_TOKEN)


def registration_authorized() -> bool:
    if not password_verified():
        return False
    if credential_count() == 0:
        return bootstrap_authorized()
    return fully_authenticated()


def require_registration_authorization():
    if not registration_authorized():
        return jsonify({"error": "security key registration is not authorized"}), 403
    return None


def require_challenge(name: str) -> bytes:
    encoded = session.pop(name, None)
    if not encoded:
        raise ValueError("authentication ceremony expired; request new options")
    return base64url_to_bytes(encoded)


@app.after_request
def security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "publickey-credentials-create=(self), publickey-credentials-get=(self)"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    if origin.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def password_verified() -> bool:
    if ADMIN_ACCOUNT is None:
        return True
    return (
        session.get("password_verified") is True
        and session.get("admin_account_fingerprint") == ADMIN_ACCOUNT.fingerprint
    )


def fully_authenticated() -> bool:
    return session.get("authenticated") is True and password_verified()


def require_password_step():
    if not password_verified():
        return jsonify({"error": "administrator username/password required first"}), 403
    return None


def establish_webauthn_session():
    # Never let WebAuthn verification clear a successfully verified password step.
    verified = password_verified()
    session.clear()
    session.permanent = True
    if ADMIN_ACCOUNT is not None and verified:
        session["password_verified"] = True
        session["admin_account_fingerprint"] = ADMIN_ACCOUNT.fingerprint
    session["authenticated"] = True


def login_lock_until() -> int:
    with db() as connection:
        row = connection.execute(
            "SELECT blocked_until FROM admin_login_failures WHERE id = 1"
        ).fetchone()
        return int(row["blocked_until"]) if row else 0


def record_failed_password_login():
    now = int(time.time())
    with db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT count, first_failed_at FROM admin_login_failures WHERE id = 1"
        ).fetchone()
        count = int(row["count"]) + 1 if row and now - row["first_failed_at"] < 900 else 1
        start = int(row["first_failed_at"]) if row and now - row["first_failed_at"] < 900 else now
        until = now + 300 if count >= 5 else 0
        connection.execute(
            """INSERT INTO admin_login_failures(id, count, first_failed_at, blocked_until)
               VALUES (1, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET count=excluded.count,
                   first_failed_at=excluded.first_failed_at, blocked_until=excluded.blocked_until""",
            (count, start, until),
        )


@app.post("/api/security/account/login")
def account_login():
    if ADMIN_ACCOUNT is None:
        return jsonify({"error": "account/password login is not configured"}), 404
    if not request.is_json:
        return jsonify({"error": "JSON request required"}), 415
    if login_lock_until() > int(time.time()):
        return jsonify({"error": "too many attempts; retry in a few minutes"}), 429

    payload = request.get_json(silent=True)
    username = payload.get("username") if isinstance(payload, dict) else None
    password = payload.get("password") if isinstance(payload, dict) else None

    if not ADMIN_ACCOUNT.verify(username, password):
        record_failed_password_login()
        return jsonify({"error": "invalid administrator credentials"}), 401

    with db() as connection:
        connection.execute("DELETE FROM admin_login_failures WHERE id = 1")
    session.clear()
    session.permanent = True
    session["password_verified"] = True
    session["admin_account_fingerprint"] = ADMIN_ACCOUNT.fingerprint
    return jsonify({"ok": True, "next_step": "webauthn"})


@app.get("/api/system/status")
def system_status():
    denied = require_authenticated()
    if denied:
        return denied

    disk = shutil.disk_usage(DATABASE_PATH.parent)
    return jsonify({
        "service": "codex-linux-server",
        "health": "ok",
        "uptime_seconds": int(time.monotonic() - STARTED_AT),
        "authentication": "password+webauthn" if ADMIN_ACCOUNT else "webauthn",
        "admin_username": ADMIN_ACCOUNT.username if ADMIN_ACCOUNT else USER_NAME,
        "security_key_registered": credential_count() > 0,
        "registered_security_keys": credential_count(),
        "encrypted_private_value_count": private_value_count(),
        "encryption_at_rest": "AES-256-GCM",
        "data_storage_path": str(DATABASE_PATH.parent),
        "storage_bytes_total": disk.total,
        "storage_bytes_free": disk.free,
        "storage_bytes_used": disk.used,
        "database_present": DATABASE_PATH.is_file(),
    })


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "authentication": "webauthn"})


@app.get("/api/security/status")
def security_status():
    return jsonify(
        {
            "security_key_required": True,
            "password_required": ADMIN_ACCOUNT is not None,
            "password_verified": password_verified() if ADMIN_ACCOUNT else False,
            "registered": credential_count() > 0,
            "authenticated": fully_authenticated(),
            "rp_id": RP_ID,
            "https_required": not is_local_origin,
            "private_data_encryption": "AES-256-GCM",
            "private_data_masked_by_default": True,
            "private_value_count": (
                private_value_count() if fully_authenticated() else None
            ),
        }
    )


@app.get("/api/security/credentials")
def security_credentials():
    if not fully_authenticated():
        return jsonify({"error": "authentication required"}), 403

    credentials = []
    for row in credential_rows():
        try:
            transports = json.loads(row["transports"])
        except (TypeError, json.JSONDecodeError):
            transports = []

        credentials.append(
            {
                "credential_id_sha256": credential_fingerprint(bytes(row["credential_id"])),
                "public_key_sha256": credential_fingerprint(bytes(row["public_key"])),
                "sign_count": int(row["sign_count"]),
                "transports": transports,
                "created_at": row["created_at"],
            }
        )

    return jsonify({"credentials": credentials, "private_key_stored": False})


@app.get("/")
def index():
    return render_template(
        "index.html",
        authenticated=fully_authenticated(),
        registered=credential_count() > 0,
        account_required=ADMIN_ACCOUNT is not None,
        password_verified=password_verified(),
    )


@app.post("/api/security/register/options")
def registration_options():
    denied = require_registration_authorization()
    if denied:
        return denied

    existing = [
        PublicKeyCredentialDescriptor(id=bytes(row["credential_id"]))
        for row in credential_rows()
    ]

    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=get_or_create_user_id(),
        user_name=USER_NAME,
        user_display_name=USER_NAME,
        exclude_credentials=existing,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.CROSS_PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        timeout=60_000,
    )
    session["registration_challenge"] = b64url_encode(options.challenge)
    return Response(options_to_json(options), mimetype="application/json")


@app.post("/api/security/register/verify")
def registration_verify():
    denied = require_registration_authorization()
    if denied:
        return denied

    credential = request.get_json(silent=True)
    if not isinstance(credential, dict):
        return jsonify({"error": "invalid credential payload"}), 400

    try:
        expected_challenge = require_challenge("registration_challenge")
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            require_user_verification=True,
        )
    except Exception as exc:
        app.logger.warning("WebAuthn registration rejected: %s", type(exc).__name__)
        return jsonify({"error": "security key registration failed"}), 400

    credential_key = b64url_encode(verification.credential_id)
    transports = credential.get("response", {}).get("transports", [])

    try:
        with db() as connection:
            connection.execute(
                """
                INSERT INTO credentials(
                    credential_key, credential_id, public_key, sign_count, transports
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    credential_key,
                    sqlite3.Binary(verification.credential_id),
                    sqlite3.Binary(verification.credential_public_key),
                    int(verification.sign_count),
                    json.dumps(transports),
                ),
            )
    except sqlite3.IntegrityError:
        return jsonify({"error": "security key is already registered"}), 409

    establish_webauthn_session()
    return jsonify({"ok": True})


@app.post("/api/security/authenticate/options")
def authentication_options():
    denied = require_password_step()
    if denied:
        return denied
    rows = credential_rows()
    if not rows:
        return jsonify({"error": "no security key has been registered"}), 409

    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=bytes(row["credential_id"])) for row in rows
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
        timeout=60_000,
    )
    session["authentication_challenge"] = b64url_encode(options.challenge)
    return Response(options_to_json(options), mimetype="application/json")


@app.post("/api/security/authenticate/verify")
def authentication_verify():
    denied = require_password_step()
    if denied:
        return denied
    credential = request.get_json(silent=True)
    if not isinstance(credential, dict) or not credential.get("id"):
        return jsonify({"error": "invalid credential payload"}), 400

    try:
        normalized_key = b64url_encode(base64url_to_bytes(credential["id"]))
        expected_challenge = require_challenge("authentication_challenge")
    except Exception:
        return jsonify({"error": "authentication ceremony expired or invalid"}), 400

    with db() as connection:
        row = connection.execute(
            """
            SELECT credential_key, credential_id, public_key, sign_count
            FROM credentials
            WHERE credential_key = ?
            """,
            (normalized_key,),
        ).fetchone()

    if not row:
        return jsonify({"error": "unknown security key"}), 403

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=bytes(row["public_key"]),
            credential_current_sign_count=int(row["sign_count"]),
            require_user_verification=True,
        )
    except Exception as exc:
        app.logger.warning("WebAuthn authentication rejected: %s", type(exc).__name__)
        return jsonify({"error": "security key authentication failed"}), 403

    with db() as connection:
        connection.execute(
            "UPDATE credentials SET sign_count = ? WHERE credential_key = ?",
            (int(verification.new_sign_count), normalized_key),
        )

    establish_webauthn_session()
    return jsonify({"ok": True})



@app.get("/api/private-values")
def list_private_values():
    denied = require_authenticated()
    if denied:
        return denied

    values = []
    for row in private_value_rows():
        try:
            payload = PRIVACY_CIPHER.decrypt(
                row["record_id"],
                row["kind"],
                bytes(row["nonce"]),
                bytes(row["ciphertext"]),
            )
            values.append(
                {
                    "id": row["record_id"],
                    "kind": row["kind"],
                    "label": payload["label"],
                    "masked_value": mask_value(row["kind"], payload["value"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "encrypted_at_rest": True,
                }
            )
        except Exception:
            app.logger.error("Unable to decrypt private value record id=%s", row["record_id"])
            values.append(
                {
                    "id": row["record_id"],
                    "kind": row["kind"],
                    "label": "[decrypt error]",
                    "masked_value": "********",
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "encrypted_at_rest": True,
                    "corrupt": True,
                }
            )

    return jsonify(
        {
            "values": values,
            "encryption": "AES-256-GCM",
            "masked_by_default": True,
            "reveal_requires_fresh_webauthn": True,
        }
    )


@app.post("/api/private-values")
def create_private_value():
    denied = require_authenticated()
    if denied:
        return denied

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid private-data payload"}), 400

    label = str(payload.get("label", "")).strip()
    value = str(payload.get("value", "")).strip()
    try:
        kind = validate_kind(str(payload.get("kind", "")))
    except ValueError:
        return jsonify({"error": "unsupported private-data kind"}), 400

    if not label or len(label) > 80:
        return jsonify({"error": "label must be 1-80 characters"}), 400
    if not value or len(value) > 512:
        return jsonify({"error": "value must be 1-512 characters"}), 400

    record_id = secrets.token_urlsafe(18)
    nonce, ciphertext = PRIVACY_CIPHER.encrypt(record_id, kind, label, value)

    with db() as connection:
        connection.execute(
            """
            INSERT INTO private_values(record_id, kind, nonce, ciphertext)
            VALUES (?, ?, ?, ?)
            """,
            (record_id, kind, sqlite3.Binary(nonce), sqlite3.Binary(ciphertext)),
        )

    return jsonify(
        {
            "id": record_id,
            "kind": kind,
            "label": label,
            "masked_value": mask_value(kind, value),
            "encrypted_at_rest": True,
        }
    ), 201


@app.patch("/api/private-values/<record_id>")
def update_private_value(record_id: str):
    denied = require_authenticated()
    if denied:
        return denied

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not ({"label", "value"} & payload.keys()):
        return jsonify({"error": "label or value is required"}), 400

    row = private_value_row(record_id)
    if row is None:
        return jsonify({"error": "private value not found"}), 404

    try:
        current = PRIVACY_CIPHER.decrypt(
            record_id, row["kind"], bytes(row["nonce"]), bytes(row["ciphertext"])
        )
    except Exception:
        app.logger.error("Unable to decrypt private value record id=%s", record_id)
        return jsonify({"error": "stored private value cannot be decrypted"}), 409

    label = str(payload["label"]).strip() if "label" in payload else current["label"]
    value = str(payload["value"]).strip() if "value" in payload else current["value"]
    if not label or len(label) > 80:
        return jsonify({"error": "label must be 1-80 characters"}), 400
    if not value or len(value) > 512:
        return jsonify({"error": "value must be 1-512 characters"}), 400

    nonce, ciphertext = PRIVACY_CIPHER.encrypt(record_id, row["kind"], label, value)
    with db() as connection:
        connection.execute(
            """
            UPDATE private_values
            SET nonce = ?, ciphertext = ?, updated_at = CURRENT_TIMESTAMP
            WHERE record_id = ?
            """,
            (sqlite3.Binary(nonce), sqlite3.Binary(ciphertext), record_id),
        )

    return jsonify(
        {
            "id": record_id,
            "kind": row["kind"],
            "label": label,
            "masked_value": mask_value(row["kind"], value),
            "encrypted_at_rest": True,
        }
    )


@app.delete("/api/private-values/<record_id>")
def delete_private_value(record_id: str):
    denied = require_authenticated()
    if denied:
        return denied

    with db() as connection:
        cursor = connection.execute(
            "DELETE FROM private_values WHERE record_id = ?",
            (record_id,),
        )
    if cursor.rowcount == 0:
        return jsonify({"error": "private value not found"}), 404
    return jsonify({"ok": True})


@app.post("/api/private-values/<record_id>/reveal/options")
def private_reveal_options(record_id: str):
    denied = require_authenticated()
    if denied:
        return denied

    if private_value_row(record_id) is None:
        return jsonify({"error": "private value not found"}), 404

    rows = credential_rows()
    if not rows:
        return jsonify({"error": "no security key has been registered"}), 409

    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=bytes(row["credential_id"])) for row in rows
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
        timeout=60_000,
    )
    session["private_reveal_challenge"] = b64url_encode(options.challenge)
    session["private_reveal_record_id"] = record_id
    return Response(options_to_json(options), mimetype="application/json")


@app.post("/api/private-values/<record_id>/reveal/verify")
def private_reveal_verify(record_id: str):
    denied = require_authenticated()
    if denied:
        return denied

    credential = request.get_json(silent=True)
    if not isinstance(credential, dict) or not credential.get("id"):
        return jsonify({"error": "invalid credential payload"}), 400

    expected_record_id = session.pop("private_reveal_record_id", None)
    if expected_record_id != record_id:
        session.pop("private_reveal_challenge", None)
        return jsonify({"error": "private reveal ceremony expired or invalid"}), 400

    try:
        normalized_key = b64url_encode(base64url_to_bytes(credential["id"]))
        expected_challenge = require_challenge("private_reveal_challenge")
    except Exception:
        return jsonify({"error": "private reveal ceremony expired or invalid"}), 400

    with db() as connection:
        credential_row = connection.execute(
            """
            SELECT credential_key, credential_id, public_key, sign_count
            FROM credentials
            WHERE credential_key = ?
            """,
            (normalized_key,),
        ).fetchone()

    if not credential_row:
        return jsonify({"error": "unknown security key"}), 403

    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=bytes(credential_row["public_key"]),
            credential_current_sign_count=int(credential_row["sign_count"]),
            require_user_verification=True,
        )
    except Exception as exc:
        app.logger.warning(
            "Private-value reveal authentication rejected: %s",
            type(exc).__name__,
        )
        return jsonify({"error": "security key authentication failed"}), 403

    with db() as connection:
        connection.execute(
            "UPDATE credentials SET sign_count = ? WHERE credential_key = ?",
            (int(verification.new_sign_count), normalized_key),
        )

    row = private_value_row(record_id)
    if row is None:
        return jsonify({"error": "private value not found"}), 404

    try:
        payload = PRIVACY_CIPHER.decrypt(
            row["record_id"],
            row["kind"],
            bytes(row["nonce"]),
            bytes(row["ciphertext"]),
        )
    except Exception:
        app.logger.error("Unable to decrypt private value record id=%s", record_id)
        return jsonify({"error": "unable to decrypt private value"}), 500

    return jsonify(
        {
            "id": record_id,
            "kind": row["kind"],
            "label": payload["label"],
            "value": payload["value"],
            "step_up_authenticated": True,
        }
    )



def _data_error(exc: DataManagerError):
    if isinstance(exc, NotFound):
        return jsonify({"error": str(exc)}), 404
    if isinstance(exc, RevisionConflict):
        return jsonify({"error": str(exc)}), 409
    return jsonify({"error": str(exc)}), 400


@app.get("/api/data/datasets")
def data_datasets():
    denied = require_authenticated()
    if denied:
        return denied
    return jsonify({"datasets": DATA_MANAGER.list_datasets()})


@app.post("/api/data/datasets")
def data_create_dataset():
    denied = require_authenticated()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body must be an object"}), 400
    try:
        result = DATA_MANAGER.create_dataset(
            str(payload.get("id", "")),
            str(payload.get("description", "")),
        )
    except DataManagerError as exc:
        return _data_error(exc)
    return jsonify(result), 201


@app.put("/api/data/datasets/<dataset_id>")
def data_update_dataset(dataset_id: str):
    denied = require_authenticated()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body must be an object"}), 400
    expected = payload.get("expected_revision")
    if expected is None:
        return jsonify({"error": "expected_revision is required for updates"}), 428
    try:
        result = DATA_MANAGER.update_dataset(
            dataset_id,
            str(payload.get("description", "")),
            int(expected),
        )
    except (TypeError, ValueError):
        return jsonify({"error": "expected_revision must be an integer"}), 400
    except DataManagerError as exc:
        return _data_error(exc)
    return jsonify(result)


@app.get("/api/data/datasets/<dataset_id>")
def data_dataset(dataset_id: str):
    denied = require_authenticated()
    if denied:
        return denied
    try:
        return jsonify(DATA_MANAGER.get_dataset(dataset_id))
    except DataManagerError as exc:
        return _data_error(exc)


@app.get("/api/data/datasets/<dataset_id>/records")
def data_records(dataset_id: str):
    denied = require_authenticated()
    if denied:
        return denied
    try:
        return jsonify({"records": DATA_MANAGER.list_records(dataset_id)})
    except DataManagerError as exc:
        return _data_error(exc)


@app.post("/api/data/datasets/<dataset_id>/records")
def data_create_record(dataset_id: str):
    denied = require_authenticated()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body must be an object"}), 400
    try:
        result = DATA_MANAGER.put_record(
            dataset_id,
            str(payload.get("id", "")),
            payload.get("data"),
            0,
        )
    except DataManagerError as exc:
        return _data_error(exc)
    return jsonify(result), 201


@app.get("/api/data/datasets/<dataset_id>/records/<record_id>")
def data_record(dataset_id: str, record_id: str):
    denied = require_authenticated()
    if denied:
        return denied
    try:
        return jsonify(DATA_MANAGER.get_record(dataset_id, record_id))
    except DataManagerError as exc:
        return _data_error(exc)


@app.put("/api/data/datasets/<dataset_id>/records/<record_id>")
def data_update_record(dataset_id: str, record_id: str):
    denied = require_authenticated()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body must be an object"}), 400
    expected = payload.get("expected_revision")
    if expected is None:
        return jsonify({"error": "expected_revision is required for updates"}), 428
    try:
        result = DATA_MANAGER.put_record(
            dataset_id,
            record_id,
            payload.get("data"),
            int(expected) if expected is not None else None,
        )
    except (TypeError, ValueError):
        return jsonify({"error": "expected_revision must be an integer"}), 400
    except DataManagerError as exc:
        return _data_error(exc)
    return jsonify(result)


@app.delete("/api/data/datasets/<dataset_id>/records/<record_id>")
def data_delete_record(dataset_id: str, record_id: str):
    denied = require_authenticated()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body must be an object"}), 400
    expected = payload.get("expected_revision")
    if expected is None:
        return jsonify({"error": "expected_revision is required for deletes"}), 428
    try:
        result = DATA_MANAGER.delete_record(
            dataset_id,
            record_id,
            int(expected) if expected is not None else None,
        )
    except (TypeError, ValueError):
        return jsonify({"error": "expected_revision must be an integer"}), 400
    except DataManagerError as exc:
        return _data_error(exc)
    return jsonify(result)


@app.get("/api/data/datasets/<dataset_id>/records/<record_id>/history")
def data_record_history(dataset_id: str, record_id: str):
    denied = require_authenticated()
    if denied:
        return denied
    try:
        return jsonify({"history": DATA_MANAGER.history(dataset_id, record_id)})
    except DataManagerError as exc:
        return _data_error(exc)


@app.get("/api/data/export")
def data_export():
    denied = require_authenticated()
    if denied:
        return denied
    dataset_id = request.args.get("dataset")
    try:
        return jsonify(DATA_MANAGER.export_bundle(dataset_id))
    except DataManagerError as exc:
        return _data_error(exc)


@app.get("/api/data/verify")
def data_verify():
    denied = require_authenticated()
    if denied:
        return denied
    dataset_id = request.args.get("dataset")
    try:
        return jsonify(DATA_MANAGER.verify(dataset_id))
    except DataManagerError as exc:
        return _data_error(exc)


@app.post("/api/security/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


init_db()
DATA_MANAGER.init_schema()
