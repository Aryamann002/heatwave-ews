"""Demand-driven forecast refresh control tests."""

import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.auth import SessionIdentity
from app.forecast_refresh import enabled, start_if_due
from app.main import _current_user, app


class ForecastRefreshTest(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {"HEATSAFE_AUTO_INGEST": "false"}):
            self.assertFalse(enabled())
            self.assertEqual(start_if_due("unused")["state"], "disabled")

    def test_current_forecast_is_not_refetched_before_six_hours(self) -> None:
        with patch.dict(os.environ, {"HEATSAFE_AUTO_INGEST": "true"}), \
             patch("app.forecast_refresh.data_status", return_value={"state": "current", "age_hours": 2}), \
             patch("app.forecast_refresh.refresh_status", return_value={"state": "idle"}) as status, \
             patch("app.forecast_refresh.psycopg.connect") as connect:
            self.assertEqual(start_if_due("db")["state"], "idle")
            status.assert_called_once_with("db")
            connect.assert_not_called()

    def test_missing_forecast_claims_one_background_run(self) -> None:
        connection = MagicMock()
        cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        with patch.dict(os.environ, {"HEATSAFE_AUTO_INGEST": "true"}), \
             patch("app.forecast_refresh.data_status", return_value={"state": "unavailable", "age_hours": None}), \
             patch("app.forecast_refresh.psycopg.connect", return_value=connection), \
             patch("app.forecast_refresh.Thread") as thread, \
             patch("app.forecast_refresh.refresh_status", return_value={"state": "running"}):
            self.assertEqual(start_if_due("db")["state"], "running")
            thread.return_value.start.assert_called_once()
            self.assertIn("next_attempt_at <= now()", cursor.execute.call_args.args[0])

    def test_unclaimed_refresh_does_not_start_a_second_worker(self) -> None:
        connection = MagicMock()
        connection.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = None
        with patch.dict(os.environ, {"HEATSAFE_AUTO_INGEST": "true"}), \
             patch("app.forecast_refresh.data_status", return_value={"state": "stale", "age_hours": 15}), \
             patch("app.forecast_refresh.psycopg.connect", return_value=connection), \
             patch("app.forecast_refresh.Thread") as thread, \
             patch("app.forecast_refresh.refresh_status", return_value={"state": "running"}):
            self.assertEqual(start_if_due("db")["state"], "running")
            thread.assert_not_called()

    def test_viewer_can_request_refresh_but_anonymous_cannot(self) -> None:
        with patch.dict(os.environ, {"AUTH_MODE": "demo"}), TestClient(app) as client:
            self.assertEqual(client.post("/forecast-refresh").status_code, 401)
            app.dependency_overrides[_current_user] = lambda: SessionIdentity("viewer-id", "viewer", "viewer")
            try:
                with patch("app.main.start_if_due", return_value={"state": "running", "message": "Fetching"}):
                    result = client.post("/forecast-refresh")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["state"], "running")
            finally:
                app.dependency_overrides.pop(_current_user, None)
