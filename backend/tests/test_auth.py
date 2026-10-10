"""Signed session tests."""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import SessionIdentity, hash_registered_password, issue_session, read_session, registration_enabled, verify_password, verify_registered_password
from app.main import app


class AuthTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["AUTH_MODE"] = "demo"

    def test_demo_password_and_signed_round_trip(self) -> None:
        self.assertTrue(verify_password("officer", "officer-demo"))
        identity = SessionIdentity("user-officer-1", "officer", "officer")
        token = issue_session(identity, now=1_000)
        self.assertEqual(read_session(token, now=1_001), identity)

    def test_rejects_tampering_and_expiry(self) -> None:
        token = issue_session(SessionIdentity("u", "officer", "officer"), now=1_000)
        with self.assertRaises(ValueError):
            read_session(token + "x", now=1_001)
        with self.assertRaises(ValueError):
            read_session(token, now=1_000 + 8 * 60 * 60)

    def test_registered_password_is_salted_and_verified(self) -> None:
        first = hash_registered_password("a long unique password")
        second = hash_registered_password("a long unique password")
        self.assertNotEqual(first, second)
        self.assertNotIn("a long unique password", first)
        self.assertTrue(verify_registered_password("a long unique password", first))
        self.assertFalse(verify_registered_password("wrong password", first))
        self.assertFalse(verify_registered_password("anything", "invalid"))

    def test_public_registration_requires_strict_opt_in(self) -> None:
        previous = os.environ.get("HEATSAFE_ALLOW_SIGNUP")
        try:
            os.environ["HEATSAFE_ALLOW_SIGNUP"] = "true"
            self.assertFalse(registration_enabled())
            os.environ["AUTH_MODE"] = "strict"
            self.assertTrue(registration_enabled())
            os.environ["HEATSAFE_ALLOW_SIGNUP"] = "false"
            self.assertFalse(registration_enabled())
        finally:
            if previous is None:
                os.environ.pop("HEATSAFE_ALLOW_SIGNUP", None)
            else:
                os.environ["HEATSAFE_ALLOW_SIGNUP"] = previous

    def test_theme_assets_are_public_in_strict_mode(self) -> None:
        with patch.dict(os.environ, {"AUTH_MODE": "strict"}):
            client = TestClient(app)
            for path in ("/theme.js", "/theme.css"):
                self.assertNotEqual(client.get(path).status_code, 401)
