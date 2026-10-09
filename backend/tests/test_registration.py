"""Database-backed viewer registration and sign-in contracts."""

import os
import unittest
import uuid
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

from app.main import app
from app.repository import ensure_operational_tables


@unittest.skipUnless(os.environ.get("DATABASE_URL"), "Postgres is required")
class RegistrationTest(unittest.TestCase):
    def test_register_login_and_duplicate(self) -> None:
        database_url = os.environ["DATABASE_URL"]
        ensure_operational_tables(database_url)
        email = f"registration-{uuid.uuid4().hex}@example.test"
        password = "A distinct test password 2026"
        env = {
            "AUTH_MODE": "strict",
            "HEATSAFE_ALLOW_SIGNUP": "true",
            "HEATWATCH_SESSION_SECRET": "registration-test-secret-32-characters-long",
            "HEATWATCH_USERS_JSON": '{"admin":"unrelated-test-password"}',
        }
        try:
            with patch.dict(os.environ, env), TestClient(app) as client:
                self.assertTrue(client.get("/auth/config").json()["email_registration"])
                result = client.post("/auth/register", json={"email": email.upper(), "password": password})
                self.assertEqual(result.status_code, 201, result.text)
                self.assertEqual(result.json()["user"]["role"], "viewer")
                self.assertEqual(result.json()["user"]["username"], email)
                token = result.json()["token"]
                self.assertEqual(client.get("/auth/session", headers={"Authorization": f"Bearer {token}"}).status_code, 200)
                self.assertEqual(client.post("/auth/register", json={"email": email, "password": password}).status_code, 409)
                self.assertEqual(client.post("/auth/login", json={"username": email, "password": "incorrect"}).status_code, 401)
                signed_in = client.post("/auth/login", json={"username": email, "password": password})
                self.assertEqual(signed_in.status_code, 200, signed_in.text)
                self.assertEqual(signed_in.json()["user"]["role"], "viewer")
                self.assertEqual(client.post("/auth/register", json={"email": "bad address", "password": password}).status_code, 422)
        finally:
            with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
                cursor.execute("DELETE FROM users WHERE username = %s", (email,))
