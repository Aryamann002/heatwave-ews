"""Signed session tests."""

import os
import unittest

from app.auth import SessionIdentity, issue_session, read_session, verify_password


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
