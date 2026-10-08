"""OAuth redirect integrity and strict-dashboard access tests (no provider network)."""

import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app
from app.oauth import authorization_url, configured_providers, make_pending, read_pending, safe_next


class OAuthContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mode = patch.dict(os.environ, {"AUTH_MODE": "demo", "HEATSAFE_GOOGLE_CLIENT_ID": "test-client", "HEATSAFE_GOOGLE_CLIENT_SECRET": "test-secret"}, clear=False)
        self.mode.start()

    def tearDown(self) -> None:
        self.mode.stop()

    def test_pending_state_is_signed_and_provider_bound(self) -> None:
        cookie, state, challenge = make_pending("google", "/dashboard.html?replay=bihar-june-2019")
        self.assertEqual(len(challenge), 43)
        self.assertEqual(read_pending(cookie, "google", state)["next"], "/dashboard.html?replay=bihar-june-2019")
        for bad_cookie, bad_provider, bad_state in ((cookie + "x", "google", state), (cookie, "github", state), (cookie, "google", "wrong")):
            with self.assertRaises(ValueError):
                read_pending(bad_cookie, bad_provider, bad_state)

    def test_only_configured_providers_are_enabled(self) -> None:
        with patch.dict(os.environ, {"HEATSAFE_GITHUB_CLIENT_ID": "", "HEATSAFE_GITHUB_CLIENT_SECRET": "", "HEATSAFE_MICROSOFT_CLIENT_ID": "", "HEATSAFE_MICROSOFT_CLIENT_SECRET": ""}):
            self.assertEqual(configured_providers(), ["google"])

    def test_authorization_url_has_exact_callback_and_pkce(self) -> None:
        url = authorization_url("google", "http://localhost:8543/auth/oauth/google/callback", "state-1", "challenge-1")
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["redirect_uri"], ["http://localhost:8543/auth/oauth/google/callback"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["state"], ["state-1"])

    def test_next_never_becomes_external_redirect(self) -> None:
        self.assertEqual(safe_next("https://example.org"), "/dashboard.html")
        self.assertEqual(safe_next("//example.org"), "/dashboard.html")
        self.assertEqual(safe_next("/dashboard.html?replay=case"), "/dashboard.html?replay=case")

    def test_strict_mode_requires_session_for_map_api(self) -> None:
        with patch.dict(os.environ, {"AUTH_MODE": "strict", "HEATWATCH_SESSION_SECRET": "x" * 40}):
            client = TestClient(app)
            self.assertEqual(client.get("/districts").status_code, 401)
            self.assertEqual(client.get("/auth/config").status_code, 200)
