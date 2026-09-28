"""Heatwave EWS HTTP API."""

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.districts import seed_districts
from app.repository import data_status, ensure_operational_tables, fetch_rows


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Seed reference districts before serving requests."""
    database_url = os.environ["DATABASE_URL"]
    seed_districts(database_url)
    ensure_operational_tables(database_url)
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
