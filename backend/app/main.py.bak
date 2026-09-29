"""Heatwave EWS HTTP API."""

import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.advisories import AdvisoryDraft, draft_advisory, lint_advisory
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
                ('user-admin-1', 'admin', 'admin')
            ON CONFLICT (user_id) DO NOTHING
            """
        )
    yield


app = FastAPI(title="Heatwave EWS", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


@app.get("/health")
def health() -> dict[str, str]:
    """Return service health without checking forecast freshness."""
    return {"status": "ok"}


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
        SELECT forecast_date AS date, tmax_c, tmin_c, relative_humidity_pct,
               wind_speed_m_s, run_id
        FROM forecast_daily WHERE district_id = %s
          AND run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
        ORDER BY forecast_date
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

    # Build start/end times from the forecast date (06:00–12:00 local)
    start = datetime.combine(date, datetime.min.time().replace(hour=6), tzinfo=UTC)
    end = datetime.combine(date, datetime.min.time().replace(hour=12), tzinfo=UTC)

    draft = draft_advisory(alert_level, district_id, start, end, language)

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
                created_at = EXCLUDED.created_at
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
               created_at, updated_at, completed_at
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
) -> dict[str, Any]:
    """Create a new response task."""
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
                 created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                "user-system-1",
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
                "user-system-1",
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
    area = ET.SubElement(info, "area")
    ET.SubElement(area, "areaDesc").text = advisory["district_id"]
    ET.SubElement(area, "polygon").text = ""

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


class DemoRunRequest(BaseModel):
    scenario: str


@app.post("/demo/run")
def run_demo(request: DemoRunRequest) -> dict[str, Any]:
    """Run a scripted demo scenario from stored data (no network)."""
    from pipeline.demo import run_demo_scenario, list_demo_scenarios
    available = list_demo_scenarios()
    if request.scenario not in available:
        raise HTTPException(status_code=404, detail=f"Scenario not found. Available: {available}")
    return run_demo_scenario(request.scenario)


@app.get("/demo/scenarios")
def list_demos() -> dict[str, Any]:
    """List available demo scenarios."""
    from pipeline.demo import list_demo_scenarios
    return {"scenarios": list_demo_scenarios()}
