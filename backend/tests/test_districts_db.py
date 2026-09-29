"""PostGIS seed and spatial-join test for pilot districts."""

import os
import unittest

import psycopg

from app.districts import seed_districts
from app.repository import ensure_operational_tables


class DistrictDatabaseTest(unittest.TestCase):
    def test_seeded_points_join_their_district_polygons(self) -> None:
        database_url = os.environ["DATABASE_URL"]
        seed_districts(database_url)
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM districts
                WHERE ST_Covers(geom, ST_SetSRID(ST_MakePoint(longitude, latitude), 4326))
                """
            )
            self.assertEqual(cursor.fetchone()[0], 3)

    def test_baseline_predictions_table_accepts_comparable_predictor_rows(self) -> None:
        database_url = os.environ["DATABASE_URL"]
        seed_districts(database_url)
        ensure_operational_tables(database_url)
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM baseline_predictions WHERE run_id = %s", ("db-test-run",))
            cursor.execute("DELETE FROM model_runs WHERE run_id = %s", ("db-test-run",))
            cursor.execute(
                "INSERT INTO model_runs VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    "db-test-run",
                    "test",
                    "2026-05-01T00:00:00Z",
                    "2026-05-01T00:00:00Z",
                    "x",
                    "pass",
                    None,
                ),
            )
            cursor.execute(
                "INSERT INTO baseline_predictions VALUES (%s,%s,%s,%s,%s,%s)",
                ("ahmedabad", "2026-05-02", "db-test-run", "persistence", 1, "yellow"),
            )
            cursor.execute(
                "SELECT baseline, lead_day, level FROM baseline_predictions WHERE run_id = %s",
                ("db-test-run",),
            )
            self.assertEqual(cursor.fetchone(), ("persistence", 1, "yellow"))

    def test_advisory_cannot_be_approved_without_human_identity_and_time(self) -> None:
        database_url = os.environ["DATABASE_URL"]
        seed_districts(database_url)
        ensure_operational_tables(database_url)
        with psycopg.connect(database_url, autocommit=True) as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM advisory_drafts WHERE run_id = %s", ("advisory-db-test",))
            cursor.execute("DELETE FROM model_runs WHERE run_id = %s", ("advisory-db-test",))
            cursor.execute(
                "INSERT INTO model_runs VALUES (%s,%s,%s,%s,%s,%s,%s)",
                ("advisory-db-test", "test", "2026-05-01T00:00:00Z", "2026-05-01T00:00:00Z", "x", "pass", None),
            )
            with self.assertRaises(psycopg.errors.CheckViolation):
                cursor.execute(
                    """
                    INSERT INTO advisory_drafts
                        (advisory_id, district_id, forecast_date, run_id, language,
                         alert_level, text, template_version, status, created_at)
                    VALUES ('invalid-approval', 'ahmedabad', '2026-05-02',
                            'advisory-db-test', 'en', 'yellow', 'test', 'test',
                            'approved', '2026-05-01T00:00:00Z')
                    """
                )
            cursor.execute("DELETE FROM model_runs WHERE run_id = %s", ("advisory-db-test",))


if __name__ == "__main__":
    unittest.main()
