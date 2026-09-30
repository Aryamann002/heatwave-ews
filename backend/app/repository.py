"""Small PostGIS repository for dashboard contracts."""

from datetime import UTC, datetime
from typing import Any

import psycopg

FRESHNESS_HOURS = 12


def ensure_operational_tables(database_url: str) -> None:
    """Create the minimal Phase 1 operational tables idempotently."""
    statements = (
        """
        CREATE TABLE IF NOT EXISTS model_runs (
            run_id text PRIMARY KEY, source text NOT NULL, init_time timestamptz NOT NULL,
            retrieved_at timestamptz NOT NULL, checksum text NOT NULL,
            qc_status text NOT NULL CHECK (qc_status IN ('pass', 'fail')),
            failure_reason text
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS forecast_daily (
            district_id text REFERENCES districts(id), forecast_date date NOT NULL,
            run_id text REFERENCES model_runs(run_id), tmax_c double precision NOT NULL,
            tmin_c double precision NOT NULL, relative_humidity_pct double precision NOT NULL,
            wind_speed_m_s double precision NOT NULL,
            PRIMARY KEY (district_id, forecast_date, run_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS thermal_indices (
            district_id text REFERENCES districts(id), forecast_date date NOT NULL,
            run_id text REFERENCES model_runs(run_id), utci_c double precision NOT NULL,
            wbgt_est_c double precision NOT NULL, heat_index_c double precision,
            PRIMARY KEY (district_id, forecast_date, run_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS alerts (
            district_id text REFERENCES districts(id), forecast_date date NOT NULL,
            run_id text REFERENCES model_runs(run_id), level text NOT NULL,
            track1_level text NOT NULL, track2_level text NOT NULL,
            disagreement boolean NOT NULL, reasoning jsonb NOT NULL,
            rule_version text NOT NULL, model_versions jsonb NOT NULL,
            issued_at timestamptz NOT NULL,
            PRIMARY KEY (district_id, forecast_date, run_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS baseline_predictions (
            district_id text REFERENCES districts(id), forecast_date date NOT NULL,
            run_id text REFERENCES model_runs(run_id), baseline text NOT NULL,
            lead_day integer NOT NULL CHECK (lead_day > 0),
            level text NOT NULL,
            PRIMARY KEY (district_id, forecast_date, run_id, baseline)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vulnerability_wards (
            ward_id text PRIMARY KEY,
            district_id text NOT NULL REFERENCES districts(id),
            name text NOT NULL,
            population_estimate double precision NOT NULL CHECK (population_estimate >= 0),
            data_vintage text NOT NULL,
            source_url text NOT NULL,
            licence text NOT NULL,
            geom geometry(MultiPolygon, 4326)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS advisory_drafts (
            advisory_id text PRIMARY KEY,
            district_id text NOT NULL REFERENCES districts(id),
            forecast_date date NOT NULL,
            run_id text NOT NULL REFERENCES model_runs(run_id),
            language text NOT NULL,
            alert_level text NOT NULL,
            text text NOT NULL,
            template_version text NOT NULL,
            status text NOT NULL DEFAULT 'pending_approval'
                CHECK (status IN ('pending_approval', 'approved', 'rejected')),
            created_at timestamptz NOT NULL,
            approved_by text,
            approved_at timestamptz,
            CHECK (
                status <> 'approved'
                OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)
            ),
            UNIQUE (district_id, forecast_date, run_id, language)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id text PRIMARY KEY,
            username text NOT NULL UNIQUE,
            role text NOT NULL CHECK (role IN ('viewer', 'officer', 'admin')),
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            audit_id text PRIMARY KEY,
            user_id text NOT NULL REFERENCES users(user_id),
            action text NOT NULL,
            entity_type text NOT NULL,
            entity_id text NOT NULL,
            old_value jsonb,
            new_value jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS response_tasks (
            task_id text PRIMARY KEY,
            district_id text NOT NULL REFERENCES districts(id),
            alert_id text,
            task_type text NOT NULL CHECK (task_type IN ('water_point', 'cooling_centre', 'ambulance_staging', 'other')),
            title text NOT NULL,
            description text,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled')),
            priority text NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'critical')),
            assigned_to text,
            location_lat double precision,
            location_lon double precision,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz
        )
        """,
    )
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
        cursor.execute("ALTER TABLE thermal_indices ALTER COLUMN heat_index_c DROP NOT NULL")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS climatology_daily (
                district_id text REFERENCES districts(id), day_of_year integer NOT NULL,
                normal_tmax_c double precision NOT NULL, p90_tmax_c double precision NOT NULL,
                p90_tmin_c double precision NOT NULL, source text NOT NULL,
                PRIMARY KEY (district_id, day_of_year)
            )
            """
        )
        # Resource allocation: tie a task to a ward and a resource quantity.
        cursor.execute("ALTER TABLE response_tasks ADD COLUMN IF NOT EXISTS ward_id text")
        cursor.execute("ALTER TABLE response_tasks ADD COLUMN IF NOT EXISTS quantity integer")
        # Regional-language advisories (LLM translations of the approved English text).
        cursor.execute("ALTER TABLE advisory_drafts DROP CONSTRAINT IF EXISTS advisory_drafts_language_check")


def data_status(database_url: str) -> dict[str, Any]:
    """Return freshness/QC state used to gate alert emission."""
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT run_id, retrieved_at, qc_status, failure_reason FROM model_runs ORDER BY init_time DESC LIMIT 1"
        )
        row = cursor.fetchone()
    if row is None:
        return {
            "state": "unavailable",
            "age_hours": None,
            "run_id": None,
            "banner": "No forecast data is available. Alerts are blocked.",
        }
    run_id, retrieved_at, qc_status, failure_reason = row
    age_hours = max(0.0, (datetime.now(UTC) - retrieved_at).total_seconds() / 3600)
    if qc_status != "pass":
        state = "qc_failed"
        banner = f"Forecast quality checks failed: {failure_reason or 'unspecified failure'}. Alerts are blocked."
    elif age_hours > FRESHNESS_HOURS:
        state = "stale"
        banner = f"Forecast data is {age_hours:.1f} hours old. Alerts are blocked."
    else:
        state = "current"
        banner = f"Forecast data is current ({age_hours:.1f} hours old)."
    return {"state": state, "age_hours": age_hours, "run_id": run_id, "banner": banner}


def fetch_rows(database_url: str, query: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Return query rows as JSON-ready dictionaries."""
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(query, parameters)
        columns = [column.name for column in cursor.description or ()]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
