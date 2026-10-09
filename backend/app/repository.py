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
        CREATE TABLE IF NOT EXISTS forecast_refresh_state (
            id integer PRIMARY KEY CHECK (id = 1),
            state text NOT NULL CHECK (state IN ('idle', 'running', 'succeeded', 'failed')),
            started_at timestamptz,
            finished_at timestamptz,
            next_attempt_at timestamptz NOT NULL DEFAULT '-infinity',
            heartbeat_at timestamptz,
            run_token text,
            detail text
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
            utci_shade_c double precision, utci_sun_c double precision,
            stress_hours integer, htsi double precision,
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
        CREATE TABLE IF NOT EXISTS registered_credentials (
            user_id text PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
            password_hash text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS oauth_identities (
            provider text NOT NULL CHECK (provider IN ('google', 'github', 'microsoft')),
            provider_subject text NOT NULL,
            user_id text NOT NULL REFERENCES users(user_id),
            display_label text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (provider, provider_subject)
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
        """
        CREATE TABLE IF NOT EXISTS health_observations (
            ward_id text NOT NULL,
            observation_date date NOT NULL,
            outcome_type text NOT NULL CHECK (
                outcome_type IN ('all_cause_mortality', 'heat_illness_admission')
            ),
            count integer NOT NULL CHECK (count >= 0),
            source_name text NOT NULL,
            source_vintage text NOT NULL,
            aggregation_note text NOT NULL,
            licence_or_agreement text NOT NULL,
            imported_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (ward_id, observation_date, outcome_type)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS district_demographics (
            district_id text PRIMARY KEY REFERENCES districts(id),
            census_state_code integer NOT NULL,
            census_district_code integer NOT NULL,
            census_national_district_code integer NOT NULL UNIQUE,
            total_population bigint NOT NULL CHECK (total_population > 0),
            elderly_60_plus bigint NOT NULL CHECK (elderly_60_plus >= 0 AND elderly_60_plus <= total_population),
            elderly_share double precision NOT NULL CHECK (elderly_share BETWEEN 0 AND 1),
            source_id text NOT NULL,
            data_vintage text NOT NULL,
            imported_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS health_reference_observations (
            source_id text NOT NULL,
            geography_level text NOT NULL CHECK (geography_level IN ('nation', 'state_or_ut')),
            geography_name text NOT NULL,
            year integer NOT NULL,
            period_end date,
            outcome_type text NOT NULL,
            count integer CHECK (count >= 0),
            count_status text NOT NULL CHECK (count_status IN ('reported', 'not_reported')),
            operational_training boolean NOT NULL DEFAULT false CHECK (operational_training = false),
            note text NOT NULL,
            imported_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (source_id, geography_name, year, outcome_type),
            CHECK ((count_status = 'reported' AND count IS NOT NULL)
                OR (count_status = 'not_reported' AND count IS NULL))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS dispatch_log (
            dispatch_id text PRIMARY KEY,
            advisory_id text NOT NULL REFERENCES advisory_drafts(advisory_id),
            channel text NOT NULL CHECK (channel IN ('sms', 'email', 'municipal_trigger')),
            idempotency_key text NOT NULL,
            actor_id text NOT NULL REFERENCES users(user_id),
            result jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (advisory_id, channel, idempotency_key)
        )
        """,
    )
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)
        cursor.execute("INSERT INTO forecast_refresh_state (id, state) VALUES (1, 'idle') ON CONFLICT (id) DO NOTHING")
        cursor.execute("ALTER TABLE forecast_refresh_state ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz")
        cursor.execute("ALTER TABLE forecast_refresh_state ADD COLUMN IF NOT EXISTS run_token text")
        cursor.execute("ALTER TABLE thermal_indices ALTER COLUMN heat_index_c DROP NOT NULL")
        cursor.execute("ALTER TABLE thermal_indices ADD COLUMN IF NOT EXISTS utci_shade_c double precision")
        cursor.execute("ALTER TABLE thermal_indices ADD COLUMN IF NOT EXISTS utci_sun_c double precision")
        cursor.execute("ALTER TABLE thermal_indices ADD COLUMN IF NOT EXISTS stress_hours integer")
        cursor.execute("ALTER TABLE thermal_indices ADD COLUMN IF NOT EXISTS htsi double precision")
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
