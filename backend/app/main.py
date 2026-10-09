"""HeatSafe AI HTTP API."""

import json
import hmac
import os
import re
import shutil
import uuid
from hashlib import sha256
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

import psycopg
import requests
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from app.advisories import IST, AdvisoryDraft, draft_advisory, lint_advisory
from app.auth import SessionIdentity, auth_mode, hash_registered_password, issue_session, public_auth_config, read_session, registration_enabled, verify_password, verify_registered_password
from app.districts import seed_districts
from app.forecast_refresh import refresh_status, start_if_due, start_uploaded
from app.forecast_upload import MAX_COMPRESSED_BYTES, stage_bundle
from app.nl_query import QueryResult, process_nl_query
from app.oauth import OAUTH_COOKIE, SESSION_COOKIE, authorization_url, client_credentials, configured_providers, exchange_identity, make_pending, public_base_url, read_pending, safe_next
from app.repository import data_status, ensure_operational_tables, fetch_rows
from indices.composite import load_weights
from models.health_data import HealthObservationBatch
from models.health_impact import load_health_impact_config, relative_risk_sensitivity
from models.ward_impact import response_priority
from pipeline.open_health_data import load_manifest, seed_open_health_reference


class SMSDispatchRequest(BaseModel):
    phone_numbers: list[str]
    idempotency_key: str = Field(min_length=8, max_length=160)


class EmailDispatchRequest(BaseModel):
    email_addresses: list[str]
    idempotency_key: str = Field(min_length=8, max_length=160)


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=4, max_length=200)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=6, max_length=80)
    password: str = Field(min_length=12, max_length=200)


class MunicipalTriggerRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)
    action_types: list[str] = Field(default_factory=list, max_length=10)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Seed reference districts before serving requests."""
    database_url = os.environ["DATABASE_URL"]
    seed_districts(database_url)
    ensure_operational_tables(database_url)
    seed_open_health_reference(database_url)
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
        if auth_mode() == "strict":
            supplied = json.loads(os.environ.get("HEATWATCH_USERS_JSON", "{}"))
            if isinstance(supplied, dict):
                for username in supplied:
                    if username in {"viewer", "officer", "admin", "system"}:
                        continue
                    user_id = f"account-{sha256(username.encode()).hexdigest()[:24]}"
                    cursor.execute("INSERT INTO users (user_id, username, role) VALUES (%s, %s, 'viewer') ON CONFLICT (username) DO NOTHING", (user_id, username))
    yield


app = FastAPI(title="HeatSafe AI", version="0.1.0", lifespan=lifespan)
_bearer = HTTPBearer(auto_error=False)


def _database_url() -> str:
    return os.environ["DATABASE_URL"]


def _current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> SessionIdentity:
    """Return the signed-in database user and reject forged/stale identities."""
    token = credentials.credentials if credentials is not None and credentials.scheme.lower() == "bearer" else request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Sign in before performing operational actions")
    try:
        identity = read_session(token)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    rows = fetch_rows(
        _database_url(),
        "SELECT user_id, username, role FROM users WHERE user_id = %s",
        (identity.user_id,),
    )
    if not rows or rows[0]["username"] != identity.username or rows[0]["role"] != identity.role:
        raise HTTPException(status_code=401, detail="Session identity no longer matches an active user")
    return identity


def _cookie_secure(request: Request) -> bool:
    # Reverse proxies may forward an internal HTTP scheme even for HTTPS users.
    # Keep local HTTP development possible, but require Secure on public strict hosts.
    return (
        os.environ.get("PUBLIC_BASE_URL", "").startswith("https://")
        or request.url.scheme == "https"
        or (auth_mode() == "strict" and request.url.hostname not in {"localhost", "127.0.0.1"})
    )


def _app_origin(request: Request) -> str:
    return os.environ.get("HEATSAFE_APP_URL", "").rstrip("/") or public_base_url(str(request.base_url))


@app.middleware("http")
async def protect_strict_dashboard_api(request: Request, call_next):
    """Keep read-only map data behind authentication on public strict deployments."""
    path = request.url.path
    public = path.startswith(("/auth/", "/assets/", "/docs", "/openapi.json")) or path in {"/", "/health", "/landing.html", "/login.html", "/signup.html", "/dashboard.html", "/favicon.ico"}
    if auth_mode() == "strict" and not public and request.method != "OPTIONS":
        header = request.headers.get("authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else request.cookies.get(SESSION_COOKIE)
        try:
            identity = read_session(token or "")
            rows = fetch_rows(_database_url(), "SELECT user_id FROM users WHERE user_id = %s AND username = %s AND role = %s", (identity.user_id, identity.username, identity.role))
            if not rows:
                raise ValueError("Account is no longer active")
        except (ValueError, RuntimeError):
            return Response(content=json.dumps({"detail": "Sign in to view the dashboard"}), status_code=401, media_type="application/json")
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


def require_roles(*roles: str):
    """FastAPI dependency factory for role-based authorization."""
    def dependency(identity: SessionIdentity = Depends(_current_user)) -> SessionIdentity:
        if identity.role not in roles:
            raise HTTPException(status_code=403, detail=f"This action requires one of these roles: {', '.join(roles)}")
        return identity

    return dependency


@app.get("/health")
def health() -> dict[str, str]:
    """Return service health without checking forecast freshness."""
    return {"status": "ok"}


@app.get("/auth/config")
def get_auth_config() -> dict[str, Any]:
    """Return public authentication mode and deployment guidance."""
    try:
        return {**public_auth_config(), "providers": configured_providers(), "email_registration": registration_enabled()}
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/auth/login")
def login(request: LoginRequest, response: Response, http_request: Request) -> dict[str, Any]:
    """Exchange environment-backed credentials for a signed eight-hour session."""
    try:
        valid = verify_password(request.username, request.password)
    except (RuntimeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    username = request.username.strip()
    if not valid and "@" in username:
        username = username.lower()
        registered = fetch_rows(
            _database_url(),
            "SELECT u.user_id, u.username, u.role, c.password_hash FROM users u JOIN registered_credentials c ON c.user_id = u.user_id WHERE u.username = %s",
            (username,),
        )
        valid = bool(registered) and verify_registered_password(request.password, registered[0]["password_hash"])
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    rows = fetch_rows(_database_url(), "SELECT user_id, username, role FROM users WHERE username = %s", (username,))
    if not rows:
        raise HTTPException(status_code=403, detail="Authenticated account is not provisioned in this deployment")
    identity = SessionIdentity(**rows[0])
    token = issue_session(identity)
    response.set_cookie(SESSION_COOKIE, token, max_age=8 * 60 * 60, httponly=True, secure=_cookie_secure(http_request), samesite="lax", path="/")
    return {"token": token, "expires_in_seconds": 8 * 60 * 60, "user": rows[0]}


@app.post("/auth/register", status_code=201)
def register(request: RegisterRequest, response: Response, http_request: Request) -> dict[str, Any]:
    """Create a new viewer account using a unique email and salted password hash."""
    if not registration_enabled():
        raise HTTPException(status_code=403, detail="Email registration is not enabled on this deployment")
    email = request.email.strip().lower()
    if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    user_id = f"registered-{uuid.uuid4()}"
    password_hash = hash_registered_password(request.password)
    try:
        with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
            cursor.execute("INSERT INTO users (user_id, username, role) VALUES (%s, %s, 'viewer') ON CONFLICT (username) DO NOTHING RETURNING user_id", (user_id, email))
            if cursor.fetchone() is None:
                raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")
            cursor.execute("INSERT INTO registered_credentials (user_id, password_hash) VALUES (%s, %s)", (user_id, password_hash))
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="Registration is temporarily unavailable. Please try again.") from error
    identity = SessionIdentity(user_id, email, "viewer")
    token = issue_session(identity)
    response.set_cookie(SESSION_COOKIE, token, max_age=8 * 60 * 60, httponly=True, secure=_cookie_secure(http_request), samesite="lax", path="/")
    return {"token": token, "expires_in_seconds": 8 * 60 * 60, "user": {"user_id": user_id, "username": email, "role": "viewer"}}


@app.post("/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    """Clear the browser's HttpOnly session cookie."""
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"signed_out": True}


@app.get("/auth/oauth/{provider}/start")
def oauth_start(provider: str, request: Request, next: str = "/dashboard.html") -> RedirectResponse:
    """Begin a provider flow with CSRF state and PKCE in a signed cookie."""
    if client_credentials(provider) is None:
        raise HTTPException(status_code=404, detail="Sign-in provider is not configured")
    try:
        base = public_base_url(str(request.base_url))
        pending, state, challenge = make_pending(provider, next)
        url = authorization_url(provider, f"{base}/auth/oauth/{provider}/callback", state, challenge)
    except ValueError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(OAUTH_COOKIE, pending, max_age=10 * 60, httponly=True, secure=_cookie_secure(request), samesite="lax", path="/auth/oauth")
    return response


@app.get("/auth/oauth/{provider}/callback")
def oauth_callback(provider: str, request: Request, code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    """Complete social sign-in and provision only a read-only viewer identity."""
    if provider not in configured_providers():
        raise HTTPException(status_code=404, detail="Sign-in provider is not configured")
    if error or not code or not state:
        return RedirectResponse(f"{_app_origin(request)}/login.html?error=provider_denied", status_code=303)
    try:
        pending = read_pending(request.cookies.get(OAUTH_COOKIE, ""), provider, state)
        base = public_base_url(str(request.base_url))
        subject, label = exchange_identity(provider, code, pending["verifier"], f"{base}/auth/oauth/{provider}/callback")
        with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT u.user_id, u.username, u.role FROM oauth_identities i JOIN users u ON u.user_id = i.user_id WHERE i.provider = %s AND i.provider_subject = %s", (provider, subject))
            row = cursor.fetchone()
            if row is None:
                user_id = f"oauth-{uuid.uuid4()}"
                username = f"{provider}:{sha256(subject.encode()).hexdigest()[:20]}"
                cursor.execute("INSERT INTO users (user_id, username, role) VALUES (%s, %s, 'viewer')", (user_id, username))
                cursor.execute("INSERT INTO oauth_identities (provider, provider_subject, user_id, display_label) VALUES (%s, %s, %s, %s)", (provider, subject, user_id, label))
                row = (user_id, username, "viewer")
        identity = SessionIdentity(*row)
        response = RedirectResponse(f"{_app_origin(request)}{safe_next(pending['next'])}", status_code=303)
        response.set_cookie(SESSION_COOKIE, issue_session(identity), max_age=8 * 60 * 60, httponly=True, secure=_cookie_secure(request), samesite="lax", path="/")
        response.delete_cookie(OAUTH_COOKIE, path="/auth/oauth")
        return response
    except (ValueError, requests.RequestException, psycopg.Error):
        return RedirectResponse(f"{_app_origin(request)}/login.html?error=provider_failed", status_code=303)


@app.get("/auth/session")
def session(identity: SessionIdentity = Depends(_current_user)) -> dict[str, Any]:
    """Return the current authenticated identity."""
    labels = fetch_rows(_database_url(), "SELECT display_label FROM oauth_identities WHERE user_id = %s LIMIT 1", (identity.user_id,))
    return {"user_id": identity.user_id, "username": identity.username, "role": identity.role, "display_name": labels[0]["display_label"] if labels else identity.username}


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
        SELECT forecast_date AS date, utci_c, utci_shade_c, utci_sun_c,
               stress_hours, htsi, wbgt_est_c, heat_index_c, run_id
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
               t.utci_c, t.utci_shade_c, t.utci_sun_c, t.stress_hours,
               t.htsi, t.wbgt_est_c, t.heat_index_c
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


@app.get("/forecast-refresh/status")
def get_forecast_refresh_status(_: SessionIdentity = Depends(_current_user)) -> dict[str, Any]:
    """Show whether an automatic forecast cycle is running or awaiting retry."""
    return refresh_status(_database_url())


@app.post("/forecast-refresh")
def request_forecast_refresh(_: SessionIdentity = Depends(_current_user)) -> dict[str, Any]:
    """Start a due cycle in the web process without blocking the dashboard."""
    return start_if_due(_database_url())


def _require_forecast_upload_token(request: Request) -> None:
    configured = os.environ.get("HEATSAFE_FORECAST_UPLOAD_TOKEN", "")
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if len(configured) < 32 or not hmac.compare_digest(supplied, configured):
        raise HTTPException(status_code=401, detail="Forecast upload is not authorized")


@app.get("/forecast-upload/status")
def uploaded_forecast_status(request: Request) -> dict[str, Any]:
    _require_forecast_upload_token(request)
    return refresh_status(_database_url())


@app.post("/forecast-upload")
async def upload_forecast(request: Request) -> dict[str, Any]:
    """Accept a small, fully checked raw forecast from the scheduled runner."""
    _require_forecast_upload_token(request)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_COMPRESSED_BYTES:
            raise HTTPException(status_code=413, detail="Forecast bundle is too large")
    try:
        run_time, root = stage_bundle(bytes(body))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        return start_uploaded(_database_url(), run_time, root)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


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


@app.get("/ward-outlook/{district_id}")
def get_ward_outlook(district_id: str, forecast_date: str) -> dict[str, Any]:
    """Rank ward response review using district hazard plus ward population exposure.

    The endpoint explicitly does not claim ward-resolution meteorology.
    """
    status = data_status(_database_url())
    if status["state"] != "current":
        raise HTTPException(status_code=409, detail=status["banner"])
    alerts = fetch_rows(
        _database_url(),
        """
        SELECT level, run_id FROM alerts WHERE district_id = %s AND forecast_date = %s
          AND run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
        """,
        (district_id, forecast_date),
    )
    if not alerts:
        raise HTTPException(status_code=404, detail="No district alert exists for this date")
    rows = fetch_rows(
        _database_url(),
        """
        SELECT ward_id, name, population_estimate, data_vintage, source_url, licence,
               ROW_NUMBER() OVER (ORDER BY population_estimate DESC, name, ward_id)::integer AS rank,
               COUNT(*) OVER ()::integer AS ward_count,
               ST_AsGeoJSON(geom, 5)::json AS geometry
        FROM vulnerability_wards WHERE district_id = %s
        ORDER BY rank
        """,
        (district_id,),
    )
    level = alerts[0]["level"]
    items = []
    for row in rows:
        result = response_priority(level, row["rank"], row["ward_count"])
        items.append({
            **row,
            "district_alert_level": level,
            "exposure_percentile": result.exposure_percentile,
            "response_priority_score": result.priority_score,
            "response_priority": result.priority,
        })
    return {
        "district_id": district_id,
        "forecast_date": forecast_date,
        "run_id": alerts[0]["run_id"],
        "status": "available" if items else "unavailable",
        "meteorology_resolution": "district point from ECMWF IFS 0.25 degree forecast",
        "ward_meteorology_downscaled": False,
        "basis": "District alert (75%) plus within-district population-exposure percentile (25%). Operational review queue only; not a ward weather forecast or health prediction.",
        "items": items,
    }


@app.get("/health-data/status")
def health_data_status() -> dict[str, Any]:
    """Report whether approved aggregated health outcomes are connected."""
    rows = fetch_rows(
        _database_url(),
        """
        SELECT COUNT(*)::integer AS rows, COUNT(DISTINCT ward_id)::integer AS wards,
               MIN(observation_date) AS first_date, MAX(observation_date) AS last_date,
               ARRAY_AGG(DISTINCT outcome_type) AS outcomes,
               ARRAY_AGG(DISTINCT source_name) AS sources
        FROM health_observations
        """,
    )
    summary = rows[0]
    connected = summary["rows"] > 0
    return {
        "status": "connected" if connected else "awaiting_approved_data",
        "operational_health_model": False,
        "absolute_outcome_forecast_enabled": False,
        "message": (
            "Aggregated ward-day health outcomes are connected; temporal validation is still required before outcome forecasts can be enabled."
            if connected
            else "No approved mortality or hospital-admission dataset is connected. The system does not fabricate outcome forecasts."
        ),
        **summary,
    }


@app.get("/health-reference/status")
def health_reference_status() -> dict[str, Any]:
    """Describe imported public context and its strict non-operational boundary."""
    demographics = fetch_rows(
        _database_url(),
        "SELECT COUNT(*)::integer AS rows, MIN(elderly_share) AS min_elderly_share, MAX(elderly_share) AS max_elderly_share FROM district_demographics",
    )[0]
    outcomes = fetch_rows(
        _database_url(),
        """
        SELECT COUNT(*)::integer AS rows, COUNT(DISTINCT source_id)::integer AS sources,
               MIN(year)::integer AS first_year, MAX(year)::integer AS last_year,
               BOOL_OR(operational_training) AS any_operational_training
        FROM health_reference_observations
        """,
    )[0]
    manifest = load_manifest()
    return {
        "status": "available" if demographics["rows"] and outcomes["rows"] else "unavailable",
        "usage": "demographic and historical context only",
        "operational_training": False,
        "warning": "Annual national/state aggregates cannot train or validate a ward-day mortality or admission model.",
        "district_demographics": demographics,
        "outcome_references": outcomes,
        "sources": [{
            "source_id": source["source_id"], "title": source["title"],
            "publisher": source["publisher"], "catalog_url": source["catalog_url"],
            "licence": source["licence"],
        } for source in manifest["sources"]],
        "attribution_notice": manifest["sources"][0]["attribution_notice"],
    }


@app.get("/demographics/{district_id}")
def get_demographics(district_id: str) -> dict[str, Any]:
    """Return Census-2011 elderly context for a mapped district."""
    rows = fetch_rows(
        _database_url(),
        """
        SELECT d.district_id, x.name AS district_name, x.state, d.total_population,
               d.elderly_60_plus, d.elderly_share, d.data_vintage, d.source_id
        FROM district_demographics d JOIN districts x ON x.id=d.district_id
        WHERE d.district_id=%s
        """,
        (district_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No Census demographic reference for this district")
    return {
        **rows[0],
        "operational_alert_input": False,
        "warning": "Census 2011 age structure is stale context and does not change the alert colour.",
    }


@app.get("/health-reference/outcomes")
def get_health_reference_outcomes(
    source_id: str | None = None,
    geography_name: str | None = None,
) -> dict[str, Any]:
    """Return public annual reference rows with optional exact-match filters."""
    rows = fetch_rows(
        _database_url(),
        """
        SELECT source_id, geography_level, geography_name, year, period_end,
               outcome_type, count, count_status, operational_training, note
        FROM health_reference_observations
        WHERE (%s::text IS NULL OR source_id=%s)
          AND (%s::text IS NULL OR geography_name=%s)
        ORDER BY source_id, geography_level, geography_name, year, outcome_type
        """,
        (source_id, source_id, geography_name, geography_name),
    )
    return {
        "usage": "historical context only",
        "operational_training": False,
        "items": rows,
    }


@app.get("/health-impact/{district_id}")
def get_health_impact(district_id: str, forecast_date: str) -> dict[str, Any]:
    """Return a non-operational relative-risk index and sensitivity scenario.

    This output never predicts counts and never participates in alert selection.
    """
    status = data_status(_database_url())
    if status["state"] != "current":
        raise HTTPException(status_code=409, detail=status["banner"])
    indices = fetch_rows(
        _database_url(),
        """
        SELECT htsi, stress_hours, utci_sun_c, utci_shade_c, run_id
        FROM thermal_indices WHERE district_id=%s AND forecast_date=%s
          AND run_id=(SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
        """,
        (district_id, forecast_date),
    )
    if not indices or indices[0]["htsi"] is None:
        raise HTTPException(status_code=409, detail="Run the radiation-aware pipeline before requesting health impact")
    wards = fetch_rows(
        _database_url(),
        """
        SELECT ward_id, name, population_estimate,
               ROW_NUMBER() OVER (ORDER BY population_estimate DESC, name, ward_id)::integer AS rank,
               COUNT(*) OVER ()::integer AS ward_count
        FROM vulnerability_wards WHERE district_id=%s ORDER BY rank
        """,
        (district_id,),
    )
    config = load_health_impact_config()
    vulnerability_weight = load_weights()["vulnerability"]
    thermal_htsi = float(indices[0]["htsi"])
    items = []
    for ward in wards:
        exposure = response_priority("green", ward["rank"], ward["ward_count"]).exposure_percentile
        score = min(1.0, thermal_htsi * (1 + vulnerability_weight * exposure) / (1 + vulnerability_weight))
        items.append({
            **ward,
            "population_exposure_percentile": exposure,
            "normalised_stress_score": round(score, 3),
            **relative_risk_sensitivity(score, config),
        })
    items.sort(key=lambda item: item["relative_risk_index"], reverse=True)
    health = health_data_status()
    return {
        "district_id": district_id,
        "forecast_date": forecast_date,
        "status": "illustrative_not_fitted" if health["status"] != "connected" else "local_data_connected_validation_pending",
        "operational_alert_input": False,
        "absolute_count_prediction": False,
        "label": "Illustrative relative heat-health risk index",
        "warning": "This is an evidence-anchored scenario, not a mortality forecast or confidence interval. Do not use it to predict deaths or admissions.",
        "method": config,
        "thermal_context": indices[0],
        "items": items,
    }


@app.post("/health-data/import")
def import_health_data(
    batch: HealthObservationBatch,
    actor: SessionIdentity = Depends(require_roles("admin")),
) -> dict[str, Any]:
    """Import approved, aggregated ward-day outcomes; raw person records are unsupported."""
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO health_observations
                (ward_id, observation_date, outcome_type, count, source_name,
                 source_vintage, aggregation_note, licence_or_agreement)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (ward_id, observation_date, outcome_type) DO UPDATE SET
                count=EXCLUDED.count, source_name=EXCLUDED.source_name,
                source_vintage=EXCLUDED.source_vintage,
                aggregation_note=EXCLUDED.aggregation_note,
                licence_or_agreement=EXCLUDED.licence_or_agreement,
                imported_at=now()
            """,
            [
                (
                    item.ward_id, item.observation_date, item.outcome_type, item.count,
                    item.source_name, item.source_vintage, item.aggregation_note,
                    batch.licence_or_agreement,
                )
                for item in batch.observations
            ],
        )
        cursor.execute(
            """
            INSERT INTO audit_log (audit_id, user_id, action, entity_type, entity_id, new_value)
            VALUES (%s,%s,'health_data_import','health_observation_batch',%s,%s)
            """,
            (
                str(uuid.uuid4()), actor.user_id, str(uuid.uuid4()),
                psycopg.types.json.Jsonb({"rows": len(batch.observations)}),
            ),
        )
    return {"status": "imported", "rows": len(batch.observations), "model_enabled": False}


@app.get("/readiness")
def product_readiness() -> dict[str, Any]:
    """Return machine-readable evidence, provenance, and deployment gates."""
    boundary = json.loads(Path("config/boundary_source.json").read_text(encoding="utf-8"))
    vulnerability = json.loads(Path("config/vulnerability_source.json").read_text(encoding="utf-8"))
    event_path = Path("data/evaluation/event_skill.json")
    event = json.loads(event_path.read_text(encoding="utf-8")) if event_path.exists() else None
    health = health_data_status()
    reference = health_reference_status()
    return {
        "product_status": "decision_support_prototype",
        "official_imd_product": False,
        "auth": public_auth_config(),
        "gates": [
            {"id": "forecast", "label": "Live 7-day forecast and stale-data blocking", "status": "pass"},
            {"id": "thermal", "label": "UTCI shade, estimated WBGT, Heat Index", "status": "pass"},
            {"id": "ward", "label": "Ward response-priority pilots", "status": "partial", "detail": "Ahmedabad, New Delhi and Chennai; meteorology remains district-scale."},
            {"id": "health", "label": "Health-outcome model", "status": "blocked" if health["status"] != "connected" else "partial", "detail": health["message"] + " Public annual reference data is available for context but is not sufficient for training."},
            {"id": "validation", "label": "Lead-day event validation", "status": "partial", "detail": "The committed event evaluation currently covers lead day 1 and 2024-2025 only."},
            {"id": "boundaries", "label": "Operational boundary approval", "status": "blocked", "detail": "Community Census 2011 boundaries must be replaced or formally accepted by the deploying authority."},
            {"id": "delivery", "label": "Authenticated approval, CAP and idempotent adapters", "status": "partial", "detail": "CAP 1.2 is emitted in Test mode; India gateway profile and telecom credentials remain deployment integrations."},
        ],
        "provenance": [
            {"layer": "Forecast", "source": "ECMWF IFS 0.25 degree via Open-Meteo", "kind": "forecast", "resolution": "district representative point"},
            {"layer": "Climatology", "source": "ERA5 1991-2020", "kind": "reanalysis", "resolution": "district daily normals"},
            {"layer": "District boundaries", "source": boundary["dataset"], "kind": "community boundary", "vintage": boundary["source_vintage"], "licence": boundary["license"]},
            {"layer": "Ward exposure", "source": "DataMeet wards plus WorldPop 2020", "kind": "proxy", "resolution": "ward population sum", "licence": vulnerability["population"]["licence"]},
            {"layer": "Health outcomes", "source": health.get("sources") or [], "kind": "approved aggregate only", "status": health["status"]},
            {"layer": "Demographic context", "source": "Census of India 2011 C-14", "kind": "district age structure", "status": reference["status"], "operational_alert_input": False},
            {"layer": "Historical heat-health context", "source": ["NPCCHH", "NCRB"], "kind": "annual national/state aggregates", "status": reference["status"], "operational_training": False},
        ],
        "event_evaluation_available": event is not None,
        "event_evaluation": event,
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
    actor: SessionIdentity = Depends(require_roles("officer", "admin")),
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
def create_regional_advisory(
    district_id: str,
    forecast_date: str,
    actor: SessionIdentity = Depends(require_roles("officer", "admin")),
) -> dict[str, Any]:
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
    english = existing[0] if existing else create_advisory(district_id, forecast_date, "en", actor)
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
def get_users(
    _: SessionIdentity = Depends(require_roles("admin")),
) -> dict[str, Any]:
    """List all users with their roles."""
    rows = fetch_rows(
        _database_url(),
        "SELECT user_id, username, role, created_at FROM users ORDER BY role, username",
    )
    return {"items": rows}


@app.patch("/advisories/{advisory_id}/approve")
def approve_advisory(
    advisory_id: str,
    action: str,  # "approve" or "reject"
    actor: SessionIdentity = Depends(require_roles("officer", "admin")),
) -> dict[str, Any]:
    """Approve or reject an advisory draft. Requires officer or admin role."""
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
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
            (new_status, actor.user_id, now, advisory_id),
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
                actor.user_id,
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
        "approved_by": actor.user_id,
        "approved_at": now.isoformat(),
    }


@app.get("/audit-log")
def get_audit_log(
    limit: int = 100,
    _: SessionIdentity = Depends(require_roles("officer", "admin")),
) -> dict[str, Any]:
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
def get_tasks(
    district_id: str,
    status_filter: str | None = None,
    _: SessionIdentity = Depends(require_roles("viewer", "officer", "admin")),
) -> dict[str, Any]:
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
    actor: SessionIdentity = Depends(require_roles("officer", "admin")),
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
                actor.user_id,
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
    actor: SessionIdentity = Depends(require_roles("officer", "admin")),
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
                actor.user_id,
                "task_update",
                "response_task",
                task_id,
                psycopg.types.json.Jsonb({"status": old_status}),
                psycopg.types.json.Jsonb(new_data),
            ),
        )

    return {"task_id": task_id, "status": status or old_status, "updated": True}


@app.delete("/tasks/{task_id}")
def delete_task(
    task_id: str,
    actor: SessionIdentity = Depends(require_roles("admin")),
) -> dict[str, Any]:
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
            (audit_id, actor.user_id, "task_delete", "response_task", task_id),
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
def export_advisory_cap(
    advisory_id: str,
    _: SessionIdentity = Depends(require_roles("officer", "admin")),
) -> dict[str, Any]:
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
    certainty_map = {"green": "Possible", "yellow": "Likely", "orange": "Likely", "red": "Likely"}

    from xml.etree import ElementTree as ET
    from xml.dom import minidom

    alert = ET.Element("alert", xmlns="urn:oasis:names:tc:emergency:cap:1.2")
    ET.SubElement(alert, "identifier").text = advisory_id
    ET.SubElement(alert, "sender").text = os.environ.get("CAP_SENDER", "heatsafe-demo@example.invalid")
    ET.SubElement(alert, "sent").text = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    ET.SubElement(alert, "status").text = os.environ.get("CAP_STATUS", "Test")
    ET.SubElement(alert, "msgType").text = "Alert"
    ET.SubElement(alert, "source").text = "HeatSafe AI"
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

    return {
        "advisory_id": advisory_id,
        "cap_xml": xml_str,
        "profile": "OASIS CAP 1.2 core",
        "integration_status": "India NDMA/IMD gateway profile review pending",
    }


def _record_dispatch_result(
    advisory_id: str,
    channel: str,
    idempotency_key: str,
    actor: SessionIdentity,
    result: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Persist one delivery result and return the original on safe retries."""
    with psycopg.connect(_database_url()) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dispatch_log
                (dispatch_id, advisory_id, channel, idempotency_key, actor_id, result)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (advisory_id, channel, idempotency_key) DO NOTHING
            RETURNING dispatch_id
            """,
            (
                str(uuid.uuid4()), advisory_id, channel, idempotency_key,
                actor.user_id, psycopg.types.json.Jsonb(result),
            ),
        )
        inserted = cursor.fetchone() is not None
        if not inserted:
            cursor.execute(
                "SELECT result FROM dispatch_log WHERE advisory_id=%s AND channel=%s AND idempotency_key=%s",
                (advisory_id, channel, idempotency_key),
            )
            return cursor.fetchone()[0], True
        cursor.execute(
            """
            INSERT INTO audit_log (audit_id, user_id, action, entity_type, entity_id, new_value)
            VALUES (%s,%s,%s,'advisory_draft',%s,%s)
            """,
            (
                str(uuid.uuid4()), actor.user_id, f"{channel}_dispatch", advisory_id,
                psycopg.types.json.Jsonb({"idempotency_key": idempotency_key}),
            ),
        )
    return result, False


@app.post("/advisories/{advisory_id}/dispatch/sms")
def dispatch_advisory_sms(
    advisory_id: str,
    request: SMSDispatchRequest,
    actor: SessionIdentity = Depends(require_roles("officer", "admin")),
) -> dict[str, Any]:
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

    result = {"advisory_id": advisory_id, "dispatched": dispatched, "total": len(dispatched)}
    stored, repeated = _record_dispatch_result(advisory_id, "sms", request.idempotency_key, actor, result)
    return {**stored, "idempotent_replay": repeated}


@app.post("/advisories/{advisory_id}/dispatch/email")
def dispatch_advisory_email(
    advisory_id: str,
    request: EmailDispatchRequest,
    actor: SessionIdentity = Depends(require_roles("officer", "admin")),
) -> dict[str, Any]:
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

    result = {"advisory_id": advisory_id, "dispatched": dispatched, "total": len(dispatched)}
    stored, repeated = _record_dispatch_result(advisory_id, "email", request.idempotency_key, actor, result)
    return {**stored, "idempotent_replay": repeated}


@app.post("/advisories/{advisory_id}/trigger/municipal")
def create_municipal_trigger(
    advisory_id: str,
    request: MunicipalTriggerRequest,
    actor: SessionIdentity = Depends(require_roles("officer", "admin")),
) -> dict[str, Any]:
    """Create an idempotent municipal trigger payload without calling an unapproved gateway."""
    rows = fetch_rows(
        _database_url(),
        """
        SELECT advisory_id, district_id, forecast_date, alert_level, text, status, approved_by
        FROM advisory_drafts WHERE advisory_id=%s
        """,
        (advisory_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="advisory not found")
    advisory = rows[0]
    if advisory["status"] != "approved":
        raise HTTPException(status_code=409, detail="only approved advisories can create municipal triggers")
    allowed = {"open_cooling_centres", "adjust_outdoor_work_hours", "stage_ambulances", "review_grid_load", "check_water_supply"}
    actions = request.action_types or ["open_cooling_centres", "adjust_outdoor_work_hours", "stage_ambulances"]
    if any(action not in allowed for action in actions):
        raise HTTPException(status_code=400, detail="unknown municipal action type")
    result = {
        "advisory_id": advisory_id,
        "district_id": advisory["district_id"],
        "forecast_date": str(advisory["forecast_date"]),
        "alert_level": advisory["alert_level"],
        "actions": actions,
        "status": "ready_for_gateway",
        "gateway": "not_configured",
        "approved_by": advisory["approved_by"],
        "created_at": datetime.now(UTC).isoformat(),
    }
    stored, repeated = _record_dispatch_result(
        advisory_id, "municipal_trigger", request.idempotency_key, actor, result
    )
    return {**stored, "idempotent_replay": repeated}

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


# Render's single-origin image includes a built frontend. Local Compose keeps
# its separate Vite service, so this mount is absent there.
_frontend_dist = Path("frontend_dist")
if _frontend_dist.is_dir():
    @app.get("/", include_in_schema=False)
    def landing_page() -> FileResponse:
        """Serve the landing page at the public root without an interstitial."""
        return FileResponse(_frontend_dist / "landing.html")

    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
