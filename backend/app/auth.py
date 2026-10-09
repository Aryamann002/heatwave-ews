"""Small signed-session layer for authenticated operational actions.

The default ``demo`` mode is intentionally labelled and uses local-only credentials.
Deployments set ``AUTH_MODE=strict``, ``HEATWATCH_SESSION_SECRET`` and
``HEATWATCH_USERS_JSON`` through environment variables.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any


SESSION_SECONDS = 8 * 60 * 60
_DEMO_SECRET = secrets.token_bytes(32)
_DEMO_PASSWORDS = {"viewer": "viewer-demo", "officer": "officer-demo", "admin": "admin-demo"}


@dataclass(frozen=True)
class SessionIdentity:
    """Authenticated identity carried by a signed session token."""

    user_id: str
    username: str
    role: str


def auth_mode() -> str:
    """Return ``demo`` or ``strict`` from deployment configuration."""
    mode = os.environ.get("AUTH_MODE", "demo").strip().lower()
    if mode not in {"demo", "strict"}:
        raise RuntimeError("AUTH_MODE must be 'demo' or 'strict'")
    return mode


def public_auth_config() -> dict[str, Any]:
    """Return non-secret login guidance for the UI."""
    mode = auth_mode()
    return {
        "mode": mode,
        "production_ready": mode == "strict",
        "banner": (
            "Strict authentication is enabled."
            if mode == "strict"
            else "Demo authentication is active. Use officer / officer-demo for the local walkthrough."
        ),
    }


def _credentials() -> dict[str, str]:
    if auth_mode() == "demo":
        return _DEMO_PASSWORDS
    raw = os.environ.get("HEATWATCH_USERS_JSON")
    if not raw:
        raise RuntimeError("HEATWATCH_USERS_JSON is required when AUTH_MODE=strict")
    value = json.loads(raw)
    if not isinstance(value, dict) or not value or any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise RuntimeError("HEATWATCH_USERS_JSON must be a non-empty username-to-password object")
    return value


def verify_password(username: str, password: str) -> bool:
    """Constant-time comparison against credentials supplied by the environment."""
    expected = _credentials().get(username)
    return expected is not None and hmac.compare_digest(expected.encode(), password.encode())


def registration_enabled() -> bool:
    """Require an explicit opt-in for public, viewer-only registration."""
    return auth_mode() == "strict" and os.environ.get("HEATSAFE_ALLOW_SIGNUP", "").strip().lower() == "true"


def hash_registered_password(password: str) -> str:
    """Store a salted, memory-hard verifier, never the submitted password."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384$8$1${_b64encode(salt)}${_b64encode(digest)}"


def verify_registered_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if (algorithm, n, r, p) != ("scrypt", "16384", "8", "1"):
            return False
        actual = hashlib.scrypt(password.encode(), salt=_b64decode(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, _b64decode(expected))
    except (ValueError, TypeError, binascii.Error):
        return False


def _secret() -> bytes:
    if auth_mode() == "demo":
        return _DEMO_SECRET
    value = os.environ.get("HEATWATCH_SESSION_SECRET")
    if not value or len(value) < 32:
        raise RuntimeError("HEATWATCH_SESSION_SECRET must contain at least 32 characters in strict mode")
    return value.encode()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_session(identity: SessionIdentity, now: int | None = None) -> str:
    """Return an HMAC-SHA256 token valid for eight hours."""
    issued = int(time.time() if now is None else now)
    payload = json.dumps(
        {"sub": identity.user_id, "username": identity.username, "role": identity.role, "iat": issued, "exp": issued + SESSION_SECONDS},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    body = _b64encode(payload)
    signature = _b64encode(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def read_session(token: str, now: int | None = None) -> SessionIdentity:
    """Verify and decode a session token, raising ``ValueError`` on any fault."""
    try:
        body, supplied = token.split(".", 1)
        expected = _b64encode(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("invalid session signature")
        payload = json.loads(_b64decode(body))
        current = int(time.time() if now is None else now)
        if current >= int(payload["exp"]):
            raise ValueError("session expired")
        return SessionIdentity(str(payload["sub"]), str(payload["username"]), str(payload["role"]))
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        raise ValueError("invalid or expired session") from error
