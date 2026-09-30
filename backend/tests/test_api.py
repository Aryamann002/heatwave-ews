"""Contract tests for the Phase 1 dashboard API."""

import json
import os
import unittest

from pipeline.s1_fetch import load_districts
from datetime import UTC, date, datetime, timedelta

import psycopg

from app.advisories import draft_advisory, lint_advisory
from app.districts import seed_districts
from app.main import (
    app,
    get_alerts,
    get_districts,
    get_forecast,
    get_indices,
    get_vulnerability,
)
from app.repository import ensure_operational_tables


class ApiContractTest(unittest.TestCase):
    run_id = "test-api-run"

    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = os.environ["DATABASE_URL"]
        seed_districts(cls.database_url)
        ensure_operational_tables(cls.database_url)

    def setUp(self) -> None:
        now = datetime.now(UTC)
        with psycopg.connect(self.database_url) as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM advisory_drafts WHERE run_id = %s", (self.run_id,))
            cursor.execute("DELETE FROM alerts WHERE run_id = %s", (self.run_id,))
            cursor.execute("DELETE FROM vulnerability_wards WHERE district_id = %s", ("ahmedabad",))
            cursor.execute("DELETE FROM thermal_indices WHERE run_id = %s", (self.run_id,))
            cursor.execute("DELETE FROM forecast_daily WHERE run_id = %s", (self.run_id,))
            cursor.execute("DELETE FROM model_runs WHERE run_id = %s", (self.run_id,))
            cursor.execute(
                "INSERT INTO model_runs VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (self.run_id, "open-meteo", now + timedelta(days=1), now, "abc123", "pass", None),
            )
            cursor.execute(
                "INSERT INTO forecast_daily VALUES (%s, %s, %s, %s, %s, %s, %s)",
                ("ahmedabad", date.today(), self.run_id, 42.0, 29.0, 45.0, 2.0),
            )
            cursor.execute(
                "INSERT INTO thermal_indices VALUES (%s, %s, %s, %s, %s, %s)",
                ("ahmedabad", date.today(), self.run_id, 39.0, 32.0, 50.0),
            )
            cursor.execute(
                "INSERT INTO alerts VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    "ahmedabad",
                    date.today(),
                    self.run_id,
                    "red",
                    "orange",
                    "red",
                    True,
                    json.dumps(["track_disagreement=true"]),
                    "imd-track1-2026-09-28",
                    json.dumps({"classifier": "not_available"}),
                    now,
                ),
            )
            cursor.executemany(
                """
                INSERT INTO vulnerability_wards
                    (ward_id, district_id, name, population_estimate, data_vintage, source_url, licence)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    ("test-low", "ahmedabad", "Test lower exposure", 100.0, "test-vintage", "test://source", "test-only"),
                    ("test-high", "ahmedabad", "Test higher exposure", 200.0, "test-vintage", "test://source", "test-only"),
                ],
            )

    def tearDown(self) -> None:
        with psycopg.connect(self.database_url) as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM advisory_drafts WHERE run_id = %s", (self.run_id,))
            cursor.execute("DELETE FROM alerts WHERE run_id = %s", (self.run_id,))
            cursor.execute("DELETE FROM vulnerability_wards WHERE district_id = %s", ("ahmedabad",))
            cursor.execute("DELETE FROM thermal_indices WHERE run_id = %s", (self.run_id,))
            cursor.execute("DELETE FROM forecast_daily WHERE run_id = %s", (self.run_id,))
            cursor.execute("DELETE FROM model_runs WHERE run_id = %s", (self.run_id,))

    def test_openapi_contains_dashboard_contracts(self) -> None:
        paths = app.openapi()["paths"]
        self.assertTrue(
            {"/districts", "/forecast/{district_id}", "/indices/{district_id}", "/alerts/{district_id}",
             "/vulnerability/{district_id}"} <= paths.keys()
        )

    def test_endpoints_return_seeded_data_and_geometry(self) -> None:
        self.assertEqual(len(get_districts()["features"]), len(load_districts()))
        self.assertEqual(get_forecast("ahmedabad")["items"][0]["tmax_c"], 42.0)
        self.assertEqual(get_indices("ahmedabad")["items"][0]["utci_c"], 39.0)
        alerts = get_alerts("ahmedabad")
        self.assertFalse(alerts["emission_blocked"])
        self.assertEqual(alerts["items"][0]["level"], "red")
        vulnerability = get_vulnerability("ahmedabad")
        self.assertEqual([item["ward_id"] for item in vulnerability["items"]], ["test-high", "test-low"])
        self.assertEqual([item["rank"] for item in vulnerability["items"]], [1, 2])
        self.assertEqual(vulnerability["data_vintage"], "test-vintage")
        self.assertEqual(vulnerability["metric"], "population_exposure")

    def test_vulnerability_is_unavailable_without_approved_rows(self) -> None:
        response = get_vulnerability("unknown-district")
        self.assertEqual(response["status"], "unavailable")
        self.assertEqual(response["items"], [])

    def test_stale_data_blocks_alert_emission(self) -> None:
        with psycopg.connect(self.database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE model_runs SET retrieved_at = %s WHERE run_id = %s",
                (datetime.now(UTC) - timedelta(hours=13), self.run_id),
            )
        alerts = get_alerts("ahmedabad")
        self.assertTrue(alerts["emission_blocked"])
        self.assertEqual(alerts["items"], [])
        self.assertEqual(alerts["data_status"]["state"], "stale")

    def test_openapi_contains_advisory_endpoints(self) -> None:
        paths = app.openapi()["paths"]
        self.assertIn("/advisories/{district_id}", paths)
        self.assertIn("get", paths["/advisories/{district_id}"])
        self.assertIn("post", paths["/advisories/{district_id}"])

    def test_advisory_generation_and_persistence(self) -> None:
        """Create an advisory draft and verify it is stored and returned."""
        today = date.today().isoformat()

        # POST creates the draft
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.post("/advisories/ahmedabad", params={"forecast_date": today, "language": "en"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["district_id"], "ahmedabad")
        self.assertEqual(data["forecast_date"], today)
        self.assertEqual(data["language"], "en")
        self.assertEqual(data["alert_level"], "red")
        self.assertIn("advisory_id", data)
        self.assertEqual(data["status"], "pending_approval")
        self.assertIn("RED heat alert", data["text"])
        self.assertIn("advisory-templates-1", data["template_version"])
        advisory_id = data["advisory_id"]

        # GET returns the stored draft
        response = client.get(f"/advisories/ahmedabad?forecast_date={today}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Filter for the advisory we just created (there may be others from manual testing)
        created = [item for item in data["items"] if item["advisory_id"] == advisory_id]
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["alert_level"], "red")
        self.assertEqual(created[0]["language"], "en")

        # Cleanup
        with psycopg.connect(self.database_url) as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM advisory_drafts WHERE advisory_id = %s", (advisory_id,))

    def test_advisory_requires_current_data(self) -> None:
        """Advisory creation is blocked when data is stale."""
        from fastapi.testclient import TestClient

        # Make data stale
        with psycopg.connect(self.database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE model_runs SET retrieved_at = %s WHERE run_id = %s",
                (datetime.now(UTC) - timedelta(hours=13), self.run_id),
            )

        client = TestClient(app)
        response = client.post(
            "/advisories/ahmedabad", params={"forecast_date": date.today().isoformat(), "language": "en"}
        )
        self.assertEqual(response.status_code, 409)

    def test_advisory_rejects_green_alert(self) -> None:
        """No advisory is generated for green alerts."""
        from fastapi.testclient import TestClient

        # Use a different date that doesn't conflict with setUp
        test_date = date.today() + timedelta(days=10)
        with psycopg.connect(self.database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO alerts VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    "ahmedabad",
                    test_date,
                    self.run_id,
                    "green",
                    "green",
                    "green",
                    False,
                    json.dumps([]),
                    "imd-track1-2026-09-28",
                    json.dumps({"classifier": "not_available"}),
                    datetime.now(UTC),
                ),
            )

        client = TestClient(app)
        response = client.post(
            "/advisories/ahmedabad", params={"forecast_date": test_date.isoformat(), "language": "en"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("green", response.json()["detail"])

        # Cleanup
        with psycopg.connect(self.database_url) as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM alerts WHERE district_id = %s AND forecast_date = %s", ("ahmedabad", test_date))

    def test_advisory_linter_enforces_template(self) -> None:
        """The linter rejects any draft that deviates from the template."""
        draft = draft_advisory(
            "orange",
            "Ahmedabad",
            datetime(2026, 5, 1, 6, tzinfo=UTC),
            datetime(2026, 5, 1, 12, tzinfo=UTC),
            "en",
        )
        # Tamper with the text
        tampered = draft.__class__(**{**draft.__dict__, "text": draft.text + " Extra unapproved content."})
        with self.assertRaisesRegex(ValueError, "approved template"):
            lint_advisory(tampered)


if __name__ == "__main__":
    unittest.main()
