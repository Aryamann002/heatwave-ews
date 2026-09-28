"""Contract tests for the Phase 1 dashboard API."""

import json
import os
import unittest
from datetime import UTC, date, datetime, timedelta

import psycopg

from app.districts import seed_districts
from app.main import app, get_alerts, get_districts, get_forecast, get_indices
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
            cursor.execute("DELETE FROM alerts WHERE run_id = %s", (self.run_id,))
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

    def tearDown(self) -> None:
        with psycopg.connect(self.database_url) as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM alerts WHERE run_id = %s", (self.run_id,))
            cursor.execute("DELETE FROM thermal_indices WHERE run_id = %s", (self.run_id,))
            cursor.execute("DELETE FROM forecast_daily WHERE run_id = %s", (self.run_id,))
            cursor.execute("DELETE FROM model_runs WHERE run_id = %s", (self.run_id,))

    def test_openapi_contains_dashboard_contracts(self) -> None:
        paths = app.openapi()["paths"]
        self.assertTrue(
            {"/districts", "/forecast/{district_id}", "/indices/{district_id}", "/alerts/{district_id}"} <= paths.keys()
        )

    def test_endpoints_return_seeded_data_and_geometry(self) -> None:
        self.assertEqual(len(get_districts()["features"]), 3)
        self.assertEqual(get_forecast("ahmedabad")["items"][0]["tmax_c"], 42.0)
        self.assertEqual(get_indices("ahmedabad")["items"][0]["utci_c"], 39.0)
        alerts = get_alerts("ahmedabad")
        self.assertFalse(alerts["emission_blocked"])
        self.assertEqual(alerts["items"][0]["level"], "red")

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


if __name__ == "__main__":
    unittest.main()
