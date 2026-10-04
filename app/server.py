import base64
import hmac
import json
import os
import secrets
import sqlite3
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, render_template, request, session
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


SESSION_SECRET = require_env("SESSION_SECRET")
RP_ID = require_env("WEBAUTHN_RP_ID")
ORIGIN = require_env("WEBAUTHN_ORIGIN").rstrip("/")
BOOTSTRAP_TOKEN = require_env("WEBAUTHN_BOOTSTRAP_TOKEN")
RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "Codex Container Server").strip()
USER_NAME = os.environ.get("WEBAUTHN_USER_NAME", "admin").strip()
DATABASE_PATH = Path(os.environ.get("WEBAUTHN_DB_PATH", "/data/webauthn.db"))

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


def credential_rows():
    with db() as connection:
        return connection.execute(
            "SELECT credential_key, credential_id, public_key, sign_count, transports FROM credentials ORDER BY created_at"
        ).fetchall()


def credential_count() -> int:
    with db() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM credentials").fetchone()
        return int(row["total"])


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
    if credential_count() == 0:
        return bootstrap_authorized()
    return session.get("authenticated") is True


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


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "authentication": "webauthn"})


@app.get("/api/security/status")
def security_status():
    return jsonify(
        {
            "security_key_required": True,
            "registered": credential_count() > 0,
            "authenticated": session.get("authenticated") is True,
            "rp_id": RP_ID,
            "https_required": not is_local_origin,
        }
    )


@app.get("/")
def index():
    return render_template(
        "index.html",
        authenticated=session.get("authenticated") is True,
        registered=credential_count() > 0,
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

    session.clear()
    session.permanent = True
    session["authenticated"] = True
    return jsonify({"ok": True})


@app.post("/api/security/authenticate/options")
def authentication_options():
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

    session.clear()
    session.permanent = True
    session["authenticated"] = True
    return jsonify({"ok": True})


@app.post("/api/security/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


init_db()
