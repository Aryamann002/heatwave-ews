"""Heatwave EWS HTTP API."""

import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.advisories import IST, AdvisoryDraft, draft_advisory, lint_advisory
from app.districts import seed_districts
from app.nl_query import QueryResult, process_nl_query
from app.repository import data_status, ensure_operational_tables, fetch_rows


class SMSDispatchRequest(BaseModel):
    phone_numbers: list[str]


class EmailDispatchRequest(BaseModel):
    email_addresses: list[str]


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Seed reference districts before serving requests."""
    database_url = os.environ["DATABASE_URL"]
    seed_districts(database_url)
    ensure_operational_tables(database_url)
    # Seed default users
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO users (user_id, username, role) VALUES
                ('user-viewer-1', 'viewer', 'viewer'),
                ('user-officer-1', 'officer', 'officer'),
                ('user-admin-1', 'admin', 'admin'),
                ('user-system-1', 'system', 'admin')
            ON CONFLICT (user_id) DO NOTHING
            """
        )
    yield


app = FastAPI(title="Heatwave EWS", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


@app.get("/health")
def health() -> dict[str, str]:
    """Return service health without checking forecast freshness."""
    return {"status": "ok"}


@app.get("/model-card")
def model_card() -> dict[str, Any]:
    """Held-out evaluation of the Tmax bias correction, or not_trained."""
    from models.train_bias import CARD_PATH

    if not CARD_PATH.exists():
        return {"status": "not_trained"}
    card = json.loads(CARD_PATH.read_text(encoding="utf-8"))
    return {"status": "trained", **card, "evaluation": {**card["evaluation"], "folds": None}}


@app.get("/districts")
def get_districts() -> dict[str, Any]:
    """Return pilot districts as WGS84 GeoJSON."""
    rows = fetch_rows(
        _database_url(),
        """
        SELECT id, name, state, climate_zone, boundary_vintage,
               ST_AsGeoJSON(geom)::json AS geometry
        FROM districts ORDER BY name
        """,
    )
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": row.pop("id"),
                "geometry": row.pop("geometry"),
                "properties": row,
            }
            for row in rows
        ],
    }


@app.get("/forecast/{district_id}")
def get_forecast(district_id: str) -> dict[str, Any]:
    """Return daily forecast values and source freshness for one district."""
    rows = fetch_rows(
        _database_url(),
        """
        SELECT f.forecast_date AS date, f.tmax_c, f.tmin_c, f.relative_humidity_pct,
               f.wind_speed_m_s, f.run_id, c.normal_tmax_c, c.p90_tmin_c,
               f.tmax_c - c.normal_tmax_c AS departure_c
        FROM forecast_daily f
        LEFT JOIN climatology_daily c ON c.district_id = f.district_id
          AND c.day_of_year = EXTRACT(DOY FROM f.forecast_date)::integer
        WHERE f.district_id = %s
          AND f.run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
        ORDER BY f.forecast_date
        """,
        (district_id,),
    )
    return {"district_id": district_id, "data_status": data_status(_database_url()), "items": rows}


@app.get("/indices/{district_id}")
def get_indices(district_id: str) -> dict[str, Any]:
    """Return daily thermal indices for one district."""
    rows = fetch_rows(
        _database_url(),
        """
        SELECT forecast_date AS date, utci_c, wbgt_est_c, heat_index_c, run_id
        FROM thermal_indices WHERE district_id = %s
          AND run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
        ORDER BY forecast_date
        """,
        (district_id,),
    )
    return {"district_id": district_id, "data_status": data_status(_database_url()), "items": rows}


@app.get("/overview")
def get_overview() -> dict[str, Any]:
    """Every district's daily level and indices for the latest run, in one call for the map."""
    status = data_status(_database_url())
    rows = fetch_rows(
        _database_url(),
        """
        SELECT a.district_id, a.forecast_date AS date, a.level, a.track1_level, a.track2_level,
               f.tmax_c, f.tmax_c - c.normal_tmax_c AS departure_c,
               t.utci_c, t.wbgt_est_c, t.heat_index_c
        FROM alerts a
        JOIN forecast_daily f USING (district_id, forecast_date, run_id)
        JOIN thermal_indices t USING (district_id, forecast_date, run_id)
        LEFT JOIN climatology_daily c ON c.district_id = a.district_id
          AND c.day_of_year = EXTRACT(DOY FROM a.forecast_date)::integer
        WHERE a.run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
        ORDER BY a.district_id, a.forecast_date
        """,
    )
    if status["state"] != "current":  # same gate as /alerts: never show stale levels
        for row in rows:
            row["level"] = row["track1_level"] = row["track2_level"] = None
    return {"data_status": status, "emission_blocked": status["state"] != "current", "items": rows}


@app.get("/alerts/{district_id}")
def get_alerts(district_id: str) -> dict[str, Any]:
    """Return alerts only when the latest source passed QC and is fresh."""
    status = data_status(_database_url())
    blocked = status["state"] != "current"
    rows = [] if blocked else fetch_rows(
        _database_url(),
        """
        SELECT forecast_date AS date, level, track1_level, track2_level,
               disagreement, reasoning, rule_version, model_versions,
               issued_at, run_id
        FROM alerts WHERE district_id = %s
          AND run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
        ORDER BY forecast_date
        """,
        (district_id,),
    )
    return {
        "district_id": district_id,
        "data_status": status,
        "emission_blocked": blocked,
        "items": rows,
    }


@app.get("/vulnerability/{district_id}")
def get_vulnerability(district_id: str) -> dict[str, Any]:
    """Rank wards by population exposure and expose source vintage."""
    rows = fetch_rows(
        _database_url(),
        """
        SELECT ward_id, name, population_estimate, data_vintage, source_url, licence,
               ST_AsGeoJSON(geom, 5)::json AS geometry,
               ROW_NUMBER() OVER (
                   ORDER BY population_estimate DESC, name, ward_id
               )::integer AS rank
        FROM vulnerability_wards
        WHERE district_id = %s
        ORDER BY rank
        """,
        (district_id,),
    )
    vintages = {row["data_vintage"] for row in rows}
    return {
        "district_id": district_id,
        "status": "available" if rows else "unavailable",
        "metric": "population_exposure",
        "data_vintage": next(iter(vintages)) if len(vintages) == 1 else "multiple" if vintages else None,
        "items": rows,
    }


@app.get("/advisories/{district_id}")
def get_advisories(district_id: str, forecast_date: str) -> dict[str, Any]:
    """Return advisory drafts for a district and forecast date."""
    try:
        date = datetime.strptime(forecast_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="forecast_date must be YYYY-MM-DD")
    rows = fetch_rows(
        _database_url(),
        """
        SELECT advisory_id, district_id, forecast_date, run_id, language,
               alert_level, text, template_version, status,
               created_at, approved_by, approved_at
        FROM advisory_drafts
        WHERE district_id = %s AND forecast_date = %s
        ORDER BY language
        """,
        (district_id, date),
    )
    return {"district_id": district_id, "forecast_date": forecast_date, "items": rows}


@app.post("/advisories/{district_id}")
def create_advisory(
    district_id: str,
    forecast_date: str,
    language: str,
) -> dict[str, Any]:
    """Generate an advisory draft from the approved template for a specific alert."""
    try:
        date = datetime.strptime(forecast_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="forecast_date must be YYYY-MM-DD")
    if language not in {"en", "hi"}:
        raise HTTPException(status_code=400, detail="language must be 'en' or 'hi'")

    status = data_status(_database_url())
    blocked = status["state"] != "current"
    if blocked:
        raise HTTPException(status_code=409, detail=status["banner"])

    # Fetch the alert for this district/date to get the deterministic alert level
    alert_rows = fetch_rows(
        _database_url(),
        """
        SELECT level FROM alerts
        WHERE district_id = %s AND forecast_date = %s
          AND run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
        """,
        (district_id, date),
    )
    if not alert_rows:
        raise HTTPException(status_code=404, detail="no alert found for this district/date")
    alert_level = alert_rows[0]["level"]
    if alert_level == "green":
        raise HTTPException(status_code=400, detail="no advisory needed for green alert")

    # Advisory window covers the peak-heat hours of the forecast day, in IST.
    start = datetime.combine(date, datetime.min.time().replace(hour=10), tzinfo=IST)
    end = datetime.combine(date, datetime.min.time().replace(hour=18), tzinfo=IST)
    names = fetch_rows(_database_url(), "SELECT name FROM districts WHERE id = %s", (district_id,))
    locality = names[0]["name"] if names else district_id

    draft = draft_advisory(alert_level, locality, start, end, language)

    # Lint to ensure template compliance
    lint_advisory(draft)

    # Persist the draft
    advisory_id = str(uuid.uuid4())
    run_id = status["run_id"]
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO advisory_drafts
                (advisory_id, district_id, forecast_date, run_id, language,
                 alert_level, text, template_version, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (district_id, forecast_date, run_id, language)
            DO UPDATE SET
                text = EXCLUDED.text,
                template_version = EXCLUDED.template_version,
                status = EXCLUDED.status,
                approved_by = NULL,
                approved_at = NULL,
                created_at = EXCLUDED.created_at
            RETURNING advisory_id
            """,
            (
                advisory_id,
                district_id,
                date,
                run_id,
                language,
                draft.alert_level,
                draft.text,
                draft.template_version,
                draft.status,
                datetime.now(UTC),
            ),
        )
        advisory_id = cursor.fetchone()[0]  # the existing id when a draft is regenerated

    return {
        "advisory_id": advisory_id,
        "district_id": district_id,
        "forecast_date": forecast_date,
        "language": language,
        "alert_level": draft.alert_level,
        "text": draft.text,
        "template_version": draft.template_version,
        "status": draft.status,
    }


# Official language(s) used for regional advisories, by state.
STATE_LANGUAGE = {
    "Gujarat": "gu", "Tamil Nadu": "ta", "Telangana": "te", "Andhra Pradesh": "te",
    "Maharashtra": "mr", "West Bengal": "bn", "Odisha": "or",
}
LANGUAGE_NAME = {"gu": "Gujarati", "ta": "Tamil", "te": "Telugu", "mr": "Marathi", "bn": "Bengali", "or": "Odia"}


@app.post("/advisories/{district_id}/regional")
def create_regional_advisory(district_id: str, forecast_date: str) -> dict[str, Any]:
    """Translate the approved-template English draft into the state's language via the LLM.

    The alert level and English text come from the deterministic path; the LLM only
    translates. The result is a separate draft that still needs officer approval.
    """
    from app.llm import MODEL, chat

    districts = fetch_rows(_database_url(), "SELECT name, state FROM districts WHERE id = %s", (district_id,))
    if not districts:
        raise HTTPException(status_code=404, detail="unknown district")
    language = STATE_LANGUAGE.get(districts[0]["state"])
    if language is None:
        raise HTTPException(status_code=400, detail="Hindi is the regional language here; use the Hindi template")
    existing = fetch_rows(
        _database_url(),
        """
        SELECT text, alert_level FROM advisory_drafts
        WHERE district_id = %s AND forecast_date = %s AND language = 'en'
          AND run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
        """,
        (district_id, forecast_date),
    )
    english = existing[0] if existing else create_advisory(district_id, forecast_date, "en")
    translated = chat(
        f"You translate official heat-wave advisories into {LANGUAGE_NAME[language]}. Translate faithfully. "
        "Keep every number, date, time, place name and the alert colour word's meaning. Add nothing. "
        "Reply with the translation only.",
        english["text"],
    )
    if not translated:
        raise HTTPException(status_code=503, detail="LLM translation unavailable (set GROQ_API_KEY); English and Hindi templates still work")
    status = data_status(_database_url())
    advisory_id = str(uuid.uuid4())
    version = f"llm-translation:{MODEL}:from-en"
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO advisory_drafts
                (advisory_id, district_id, forecast_date, run_id, language,
                 alert_level, text, template_version, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending_approval', %s)
            ON CONFLICT (district_id, forecast_date, run_id, language)
            DO UPDATE SET text = EXCLUDED.text, template_version = EXCLUDED.template_version,
                status = 'pending_approval', approved_by = NULL, approved_at = NULL,
                created_at = EXCLUDED.created_at
            """,
            (advisory_id, district_id, forecast_date, status["run_id"], language,
             english["alert_level"], translated, version, datetime.now(UTC)),
        )
        cursor.execute(
            "SELECT advisory_id FROM advisory_drafts WHERE district_id = %s AND forecast_date = %s AND run_id = %s AND language = %s",
            (district_id, forecast_date, status["run_id"], language),
        )
        advisory_id = cursor.fetchone()[0]
    return {"advisory_id": advisory_id, "language": language, "text": translated, "template_version": version, "status": "pending_approval"}


@app.get("/users")
def get_users() -> dict[str, Any]:
    """List all users with their roles."""
    rows = fetch_rows(
        _database_url(),
        "SELECT user_id, username, role, created_at FROM users ORDER BY role, username",
    )
    return {"items": rows}


@app.patch("/advisories/{advisory_id}/approve")
def approve_advisory(
    advisory_id: str,
    user_id: str,
    action: str,  # "approve" or "reject"
) -> dict[str, Any]:
    """Approve or reject an advisory draft. Requires officer or admin role."""
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        # Verify user exists and has officer/admin role
        cursor.execute("SELECT role FROM users WHERE user_id = %s", (user_id,))
        user_row = cursor.fetchone()
        if not user_row:
            raise HTTPException(status_code=403, detail="user not found")
        if user_row[0] not in ("officer", "admin"):
            raise HTTPException(status_code=403, detail="only officers and admins can approve/reject advisories")

        # Fetch current advisory
        advisory_rows = fetch_rows(
            _database_url(),
            """
            SELECT advisory_id, district_id, forecast_date, run_id, language,
                   alert_level, text, template_version, status, created_at
            FROM advisory_drafts WHERE advisory_id = %s
            """,
            (advisory_id,),
        )
        if not advisory_rows:
            raise HTTPException(status_code=404, detail="advisory not found")
        advisory = advisory_rows[0]

        if advisory["status"] != "pending_approval":
            raise HTTPException(status_code=409, detail=f"advisory already {advisory['status']}")

        if action not in ("approve", "reject"):
            raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

        new_status = "approved" if action == "approve" else "rejected"
        now = datetime.now(UTC)

        # Update advisory
        cursor.execute(
            """
            UPDATE advisory_drafts
            SET status = %s, approved_by = %s, approved_at = %s
            WHERE advisory_id = %s
            """,
            (new_status, user_id, now, advisory_id),
        )

        # Log to audit
        audit_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO audit_log (audit_id, user_id, action, entity_type, entity_id, old_value, new_value)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                audit_id,
                user_id,
                f"advisory_{action}",
                "advisory_draft",
                advisory_id,
                psycopg.types.json.Jsonb({"status": advisory["status"]}),
                psycopg.types.json.Jsonb({"status": new_status}),
            ),
        )

    return {
        "advisory_id": advisory_id,
        "status": new_status,
        "approved_by": user_id,
        "approved_at": now.isoformat(),
    }


@app.get("/audit-log")
def get_audit_log(limit: int = 100) -> dict[str, Any]:
    """Return audit log entries."""
    rows = fetch_rows(
        _database_url(),
        """
        SELECT audit_id, user_id, action, entity_type, entity_id,
               old_value, new_value, created_at
        FROM audit_log ORDER BY created_at DESC LIMIT %s
        """,
        (limit,),
    )
    return {"items": rows}


@app.get("/tasks/{district_id}")
def get_tasks(district_id: str, status_filter: str | None = None) -> dict[str, Any]:
    """Return response tasks for a district, optionally filtered by status."""
    query = """
        SELECT task_id, district_id, alert_id, task_type, title, description,
               status, priority, assigned_to, location_lat, location_lon,
               ward_id, quantity, created_at, updated_at, completed_at
        FROM response_tasks WHERE district_id = %s
    """
    params: list[Any] = [district_id]
    if status_filter:
        query += " AND status = %s"
        params.append(status_filter)
    query += " ORDER BY created_at DESC"
    rows = fetch_rows(_database_url(), query, tuple(params))
    return {"district_id": district_id, "items": rows}


@app.post("/tasks/{district_id}")
def create_task(
    district_id: str,
    task_type: str,
    title: str,
    description: str | None = None,
    priority: str = "normal",
    assigned_to: str | None = None,
    location_lat: float | None = None,
    location_lon: float | None = None,
    alert_id: str | None = None,
    ward_id: str | None = None,
    quantity: int | None = None,
    user_id: str = "user-system-1",
) -> dict[str, Any]:
    """Create a new response task, optionally allocating a resource quantity to a ward."""
    if task_type not in {"water_point", "cooling_centre", "ambulance_staging", "other"}:
        raise HTTPException(status_code=400, detail="invalid task_type")
    if priority not in {"low", "normal", "high", "critical"}:
        raise HTTPException(status_code=400, detail="invalid priority")

    task_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO response_tasks
                (task_id, district_id, alert_id, task_type, title, description,
                 status, priority, assigned_to, location_lat, location_lon,
                 created_at, updated_at, ward_id, quantity)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                task_id,
                district_id,
                alert_id,
                task_type,
                title,
                description,
                "pending",
                priority,
                assigned_to,
                location_lat,
                location_lon,
                now,
                now,
                ward_id,
                quantity,
            ),
        )

        # Audit log
        audit_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO audit_log (audit_id, user_id, action, entity_type, entity_id, new_value)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                audit_id,
                user_id,
                "task_create",
                "response_task",
                task_id,
                psycopg.types.json.Jsonb({"task_type": task_type, "title": title}),
            ),
        )

    return {
        "task_id": task_id,
        "district_id": district_id,
        "task_type": task_type,
        "title": title,
        "status": "pending",
        "priority": priority,
    }


@app.patch("/tasks/{task_id}")
def update_task(
    task_id: str,
    status: str | None = None,
    priority: str | None = None,
    assigned_to: str | None = None,
    description: str | None = None,
    user_id: str = "user-system-1",
) -> dict[str, Any]:
    """Update a response task."""
    if status and status not in {"pending", "in_progress", "completed", "cancelled"}:
        raise HTTPException(status_code=400, detail="invalid status")
    if priority and priority not in {"low", "normal", "high", "critical"}:
        raise HTTPException(status_code=400, detail="invalid priority")

    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        rows = fetch_rows(_database_url(), "SELECT * FROM response_tasks WHERE task_id = %s", (task_id,))
        if not rows:
            raise HTTPException(status_code=404, detail="task not found")

        row = rows[0]
        old_status = row["status"]
        updates = []
        params = []
        if status is not None:
            updates.append("status = %s")
            params.append(status)
        if priority is not None:
            updates.append("priority = %s")
            params.append(priority)
        if assigned_to is not None:
            updates.append("assigned_to = %s")
            params.append(assigned_to)
        if description is not None:
            updates.append("description = %s")
            params.append(description)
        if status == "completed" and old_status != "completed":
            updates.append("completed_at = %s")
            params.append(datetime.now(UTC))

        if not updates:
            raise HTTPException(status_code=400, detail="no fields to update")

        updates.append("updated_at = %s")
        params.append(datetime.now(UTC))
        params.append(task_id)

        cursor.execute(
            f"UPDATE response_tasks SET {', '.join(updates)} WHERE task_id = %s",
            tuple(params),
        )

        # Audit log
        audit_id = str(uuid.uuid4())
        new_data = {}
        if status is not None:
            new_data["status"] = status
        if priority is not None:
            new_data["priority"] = priority
        if assigned_to is not None:
            new_data["assigned_to"] = assigned_to
        if description is not None:
            new_data["description"] = description
        cursor.execute(
            """
            INSERT INTO audit_log (audit_id, user_id, action, entity_type, entity_id, old_value, new_value)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                audit_id,
                user_id,
                "task_update",
                "response_task",
                task_id,
                psycopg.types.json.Jsonb({"status": old_status}),
                psycopg.types.json.Jsonb(new_data),
            ),
        )

    return {"task_id": task_id, "status": status or old_status, "updated": True}


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str) -> dict[str, Any]:
    """Delete a response task."""
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT * FROM response_tasks WHERE task_id = %s", (task_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="task not found")

        cursor.execute("DELETE FROM response_tasks WHERE task_id = %s", (task_id,))

        # Audit log
        audit_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO audit_log (audit_id, user_id, action, entity_type, entity_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (audit_id, "user-system-1", "task_delete", "response_task", task_id),
        )

    return {"task_id": task_id, "deleted": True}


# Planning ratios (people served per unit) used only to *suggest* an allocation; the officer
# edits quantities before creating tasks. ponytail: flat ratios, replace with state SOPs.
RESOURCE_RATIOS = {"water_point": 25_000, "cooling_centre": 50_000, "ambulance_staging": 100_000}
LEVEL_WEIGHT = {"yellow": 0.5, "orange": 1.0, "red": 1.5}


@app.get("/allocation/{district_id}")
def suggest_allocation(district_id: str, forecast_date: str, top: int = 8) -> dict[str, Any]:
    """Suggest resources for the most-exposed wards, scaled by the day's alert level."""
    status = data_status(_database_url())
    if status["state"] != "current":
        raise HTTPException(status_code=409, detail=status["banner"])
    alert = fetch_rows(
        _database_url(),
        """
        SELECT level FROM alerts WHERE district_id = %s AND forecast_date = %s
          AND run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
        """,
        (district_id, forecast_date),
    )
    level = alert[0]["level"] if alert else "green"
    weight = LEVEL_WEIGHT.get(level, 0.0)
    wards = fetch_rows(
        _database_url(),
        """
        SELECT ward_id, name, population_estimate,
               ST_Y(ST_PointOnSurface(geom)) AS lat, ST_X(ST_PointOnSurface(geom)) AS lon
        FROM vulnerability_wards WHERE district_id = %s
        ORDER BY population_estimate DESC LIMIT %s
        """,
        (district_id, top),
    )
    items = [
        {
            **ward,
            "resources": {
                kind: max(1, round(ward["population_estimate"] * weight / people))
                for kind, people in RESOURCE_RATIOS.items()
            } if weight else {},
        }
        for ward in wards
    ]
    return {
        "district_id": district_id,
        "forecast_date": forecast_date,
        "alert_level": level,
        "basis": "population exposure x alert weight; planning ratios are editable assumptions",
        "ratios_people_per_unit": RESOURCE_RATIOS,
        "items": items,
    }


@app.get("/advisories/{advisory_id}/cap")
def export_advisory_cap(advisory_id: str) -> dict[str, Any]:
    """Export an approved advisory as CAP 1.2 XML."""
    rows = fetch_rows(
        _database_url(),
        """
        SELECT advisory_id, district_id, forecast_date, run_id, language,
               alert_level, text, template_version, status, created_at, approved_by, approved_at
        FROM advisory_drafts WHERE advisory_id = %s
        """,
        (advisory_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="advisory not found")
    advisory = rows[0]

    if advisory["status"] != "approved":
        raise HTTPException(status_code=409, detail="only approved advisories can be exported as CAP")

    # Map alert level to CAP severity
    severity_map = {"green": "Minor", "yellow": "Moderate", "orange": "Severe", "red": "Extreme"}
    urgency_map = {"green": "Past", "yellow": "Future", "orange": "Immediate", "red": "Immediate"}
    certainty_map = {"green": "Observed", "yellow": "Likely", "orange": "Likely", "red": "Observed"}

    from xml.etree import ElementTree as ET
    from xml.dom import minidom

    alert = ET.Element("alert", xmlns="urn:oasis:names:tc:emergency:cap:1.2")
    ET.SubElement(alert, "identifier").text = advisory_id
    ET.SubElement(alert, "sender").text = "heatwave-ews@gov.in"
    ET.SubElement(alert, "sent").text = datetime.now(UTC).isoformat()
    ET.SubElement(alert, "status").text = "Actual"
    ET.SubElement(alert, "msgType").text = "Alert"
    ET.SubElement(alert, "source").text = "Heatwave EWS"
    ET.SubElement(alert, "scope").text = "Public"

    info = ET.SubElement(alert, "info")
    ET.SubElement(info, "language").text = advisory["language"]
    ET.SubElement(info, "category").text = "Met"
    ET.SubElement(info, "event").text = "Heatwave"
    ET.SubElement(info, "responseType").text = "Shelter"
    ET.SubElement(info, "urgency").text = urgency_map.get(advisory["alert_level"], "Future")
    ET.SubElement(info, "severity").text = severity_map.get(advisory["alert_level"], "Moderate")
    ET.SubElement(info, "certainty").text = certainty_map.get(advisory["alert_level"], "Likely")
    ET.SubElement(info, "description").text = advisory["text"]
    ET.SubElement(info, "instruction").text = advisory["text"]

    # Area
    # CAP polygons must be a single closed ring of "lat,lon" pairs; the convex hull of
    # the district boundary is a conservative (slightly larger) outline.
    district = fetch_rows(
        _database_url(),
        """
        SELECT name, state, ST_AsGeoJSON(ST_ExteriorRing(ST_ConvexHull(geom)), 4) AS ring
        FROM districts WHERE id = %s
        """,
        (advisory["district_id"],),
    )
    area = ET.SubElement(info, "area")
    if district:
        ring = json.loads(district[0]["ring"])["coordinates"]
        ET.SubElement(area, "areaDesc").text = f"{district[0]['name']}, {district[0]['state']}"
        ET.SubElement(area, "polygon").text = " ".join(f"{lat},{lon}" for lon, lat in ring)
    else:
        ET.SubElement(area, "areaDesc").text = advisory["district_id"]

    # Parameter
    param = ET.SubElement(info, "parameter")
    ET.SubElement(param, "valueName").text = "alertLevel"
    ET.SubElement(param, "value").text = advisory["alert_level"].upper()

    # Convert to pretty XML
    rough = ET.tostring(alert, encoding="unicode")
    reparsed = minidom.parseString(rough)
    xml_str = reparsed.toprettyxml(indent="  ")

    return {"advisory_id": advisory_id, "cap_xml": xml_str}


@app.post("/advisories/{advisory_id}/dispatch/sms")
def dispatch_advisory_sms(advisory_id: str, request: SMSDispatchRequest) -> dict[str, Any]:
    """Mock SMS dispatch for an approved advisory."""
    rows = fetch_rows(
        _database_url(),
        """
        SELECT advisory_id, district_id, alert_level, text, language, status
        FROM advisory_drafts WHERE advisory_id = %s
        """,
        (advisory_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="advisory not found")
    advisory = rows[0]

    if advisory["status"] != "approved":
        raise HTTPException(status_code=409, detail="only approved advisories can be dispatched")

    if not request.phone_numbers:
        raise HTTPException(status_code=400, detail="phone_numbers list cannot be empty")

    # Mock dispatch - in production this would integrate with an SMS gateway
    dispatched = []
    for phone in request.phone_numbers:
        dispatched.append({
            "phone": phone,
            "message": advisory["text"][:160],  # SMS length limit
            "status": "sent",
            "provider": "mock-sms-gateway",
            "sent_at": datetime.now(UTC).isoformat(),
        })

    # Audit log
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        audit_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO audit_log (audit_id, user_id, action, entity_type, entity_id, new_value)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                audit_id,
                "user-system-1",
                "sms_dispatch",
                "advisory_draft",
                advisory_id,
                psycopg.types.json.Jsonb({"recipients": len(request.phone_numbers)}),
            ),
        )

    return {"advisory_id": advisory_id, "dispatched": dispatched, "total": len(dispatched)}


@app.post("/advisories/{advisory_id}/dispatch/email")
def dispatch_advisory_email(advisory_id: str, request: EmailDispatchRequest) -> dict[str, Any]:
    """Mock email dispatch for an approved advisory."""
    rows = fetch_rows(
        _database_url(),
        """
        SELECT advisory_id, district_id, alert_level, text, language, status
        FROM advisory_drafts WHERE advisory_id = %s
        """,
        (advisory_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="advisory not found")
    advisory = rows[0]

    if advisory["status"] != "approved":
        raise HTTPException(status_code=409, detail="only approved advisories can be dispatched")

    if not request.email_addresses:
        raise HTTPException(status_code=400, detail="email_addresses list cannot be empty")

    # Mock dispatch - in production this would integrate with an email service
    dispatched = []
    for email in request.email_addresses:
        dispatched.append({
            "email": email,
            "subject": f"Heatwave Alert: {advisory['alert_level'].upper()} for {advisory['district_id']}",
            "body": advisory["text"],
            "status": "sent",
            "provider": "mock-email-gateway",
            "sent_at": datetime.now(UTC).isoformat(),
        })

    # Audit log
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        audit_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO audit_log (audit_id, user_id, action, entity_type, entity_id, new_value)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                audit_id,
                "user-system-1",
                "email_dispatch",
                "advisory_draft",
                advisory_id,
                psycopg.types.json.Jsonb({"recipients": len(request.email_addresses)}),
            ),
        )

    return {"advisory_id": advisory_id, "dispatched": dispatched, "total": len(dispatched)}

class NLQueryRequest(BaseModel):
    query: str


@app.post("/query")
def nl_query(request: NLQueryRequest) -> dict[str, Any]:
    """Process a natural language query about dashboard data."""
    result = process_nl_query(request.query)
    return {
        "query": request.query,
        "answer": result.answer,
        "data": result.data,
        "query_type": result.query_type,
    }


@app.get("/replay/scenarios")
def list_replays() -> dict[str, Any]:
    """Real historical heatwaves that can be replayed through the live alert code."""
    from pipeline.replay import load_scenarios

    document = load_scenarios()
    return {"note": document["note"], "scenarios": document["scenarios"]}


@app.get("/replay/{scenario_id}")
def get_replay(scenario_id: str) -> dict[str, Any]:
    """Replay one scenario: ERA5 hourly data -> same indices and alert rules as the live path."""
    from pipeline.replay import run_replay

    try:
        return run_replay(scenario_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown scenario")
    except OSError as error:  # network failure on first (uncached) run
        raise HTTPException(status_code=503, detail=f"replay data unavailable: {error}")
