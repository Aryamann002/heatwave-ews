"""Server-side OAuth authorization-code helpers for optional social sign-in."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

import requests

from app.auth import _secret


OAUTH_COOKIE = "heatsafe_oauth_pending"
SESSION_COOKIE = "heatsafe_session"
PENDING_SECONDS = 10 * 60


@dataclass(frozen=True)
class Provider:
    name: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scope: str


PROVIDERS = {
    "google": Provider("google", "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token", "https://openidconnect.googleapis.com/v1/userinfo", "openid email profile"),
    "github": Provider("github", "https://github.com/login/oauth/authorize", "https://github.com/login/oauth/access_token", "https://api.github.com/user", "read:user"),
    "microsoft": Provider("microsoft", "https://login.microsoftonline.com/common/oauth2/v2.0/authorize", "https://login.microsoftonline.com/common/oauth2/v2.0/token", "https://graph.microsoft.com/oidc/userinfo", "openid profile email"),
}


def configured_providers() -> list[str]:
    """Return providers with both server-side client credentials configured."""
    return [name for name in PROVIDERS if client_credentials(name) is not None]


def client_credentials(provider: str) -> tuple[str, str] | None:
    if provider not in PROVIDERS:
        return None
    prefix = f"HEATSAFE_{provider.upper()}"
    client_id = os.environ.get(f"{prefix}_CLIENT_ID", "").strip()
    client_secret = os.environ.get(f"{prefix}_CLIENT_SECRET", "").strip()
    return (client_id, client_secret) if client_id and client_secret else None


def public_base_url(request_base: str) -> str:
    """Use a configured public origin, allowing implicit origins only on localhost."""
    configured = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    base = configured or request_base.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path not in {"", "/"}:
        raise ValueError("PUBLIC_BASE_URL must be a public origin without a path")
    if not configured and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("PUBLIC_BASE_URL must be configured for deployed OAuth sign-in")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Deployed OAuth sign-in requires HTTPS")
    return base


def safe_next(value: str | None) -> str:
    """Restrict post-login navigation to the map page on this origin."""
    candidate = value or "/dashboard.html"
    if candidate == "/dashboard.html" or candidate.startswith("/dashboard.html?replay="):
        if not any(char in candidate for char in "\\\r\n#") and not candidate.startswith("//"):
            return candidate
    return "/dashboard.html"


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def make_pending(provider: str, next_path: str) -> tuple[str, str, str]:
    """Create a signed, short-lived browser transaction and PKCE challenge."""
    if provider not in PROVIDERS:
        raise ValueError("Unknown sign-in provider")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    payload = json.dumps({"provider": provider, "state": state, "verifier": verifier, "next": safe_next(next_path), "exp": int(time.time()) + PENDING_SECONDS}, separators=(",", ":")).encode()
    body = _encode(payload)
    signature = _encode(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    challenge = _encode(hashlib.sha256(verifier.encode()).digest())
    return f"{body}.{signature}", state, challenge


def read_pending(cookie: str, provider: str, state: str) -> dict[str, str]:
    """Reject tampered, expired or cross-provider callback transactions."""
    try:
        body, supplied = cookie.split(".", 1)
        expected = _encode(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, supplied):
            raise ValueError("Invalid sign-in state")
        payload = json.loads(_decode(body))
        if int(payload["exp"]) < int(time.time()) or payload["provider"] != provider or not hmac.compare_digest(payload["state"], state):
            raise ValueError("Expired or mismatched sign-in state")
        return {"verifier": str(payload["verifier"]), "next": safe_next(str(payload["next"]))}
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        raise ValueError("Invalid or expired sign-in state") from error


def authorization_url(provider: str, redirect_uri: str, state: str, challenge: str) -> str:
    credentials = client_credentials(provider)
    if credentials is None:
        raise ValueError("Sign-in provider is not configured")
    params = {"client_id": credentials[0], "redirect_uri": redirect_uri, "response_type": "code", "scope": PROVIDERS[provider].scope, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    return f"{PROVIDERS[provider].authorize_url}?{urlencode(params)}"


def exchange_identity(provider: str, code: str, verifier: str, redirect_uri: str) -> tuple[str, str]:
    """Exchange one code and read the provider's stable user ID and display label."""
    credentials = client_credentials(provider)
    if credentials is None:
        raise ValueError("Sign-in provider is not configured")
    config = PROVIDERS[provider]
    response = requests.post(config.token_url, data={"client_id": credentials[0], "client_secret": credentials[1], "code": code, "code_verifier": verifier, "redirect_uri": redirect_uri, "grant_type": "authorization_code"}, headers={"Accept": "application/json"}, timeout=12)
    response.raise_for_status()
    access_token = response.json().get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("Provider did not issue an access token")
    identity_response = requests.get(config.userinfo_url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json", "User-Agent": "HeatSafe-AI/1.0"}, timeout=12)
    identity_response.raise_for_status()
    profile = identity_response.json()
    subject = profile.get("id") if provider == "github" else profile.get("sub")
    if subject is None or not str(subject):
        raise ValueError("Provider did not return a stable user ID")
    if provider == "google" and profile.get("email_verified") is True:
        label = profile.get("email") or profile.get("name") or "Google viewer"
    elif provider == "github":
        label = profile.get("login") or "GitHub viewer"
    else:
        label = profile.get("name") or profile.get("email") or "Microsoft viewer"
    return str(subject), str(label)[:80]
