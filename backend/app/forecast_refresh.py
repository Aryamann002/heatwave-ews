"""Bounded on-demand forecast refresh for a free, sleeping web service.

This is not a scheduler: an authenticated dashboard request starts work only
when the configured forecast has become old, and the job runs in this process.
The database claim prevents multiple visitors from starting duplicate cycles.
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import UTC, datetime
from threading import Event, Thread
from typing import Any
from uuid import uuid4
from pathlib import Path

import psycopg

from app.repository import data_status

LOG = logging.getLogger(__name__)
MIN_REFRESH_AGE_HOURS = 6


def enabled() -> bool:
    return (os.environ.get("HEATSAFE_AUTO_INGEST", "").strip().lower() == "true"
            and not os.environ.get("HEATSAFE_FORECAST_UPLOAD_TOKEN"))


def refresh_status(database_url: str) -> dict[str, Any]:
    """Return a small, public-safe status without raw upstream error details."""
    if not enabled() and not os.environ.get("HEATSAFE_FORECAST_UPLOAD_TOKEN"):
        return {"state": "disabled", "message": "Automatic forecast refresh is not enabled on this deployment."}
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT state, started_at, finished_at, detail FROM forecast_refresh_state WHERE id = 1")
        row = cursor.fetchone()
    if row is None:
        return {"state": "idle", "message": "Forecast refresh is ready."}
    state, started_at, finished_at, detail = row
    messages = {
        "idle": "Forecast refresh is ready.",
        "running": "Fetching and checking the seven-day forecast. This can take several minutes.",
        "succeeded": "Forecast refresh completed.",
        "failed": "Forecast refresh failed; the data-quality gate remains active. Another attempt will be available shortly.",
    }
    return {
        "state": state,
        "message": messages[state],
        "started_at": started_at,
        "finished_at": finished_at,
        "detail": detail if state == "failed" else None,
    }


def start_if_due(database_url: str) -> dict[str, Any]:
    """Atomically claim a due refresh and return immediately to the visitor."""
    if not enabled():
        return refresh_status(database_url)
    forecast = data_status(database_url)
    if forecast["state"] == "current" and (forecast["age_hours"] or 0) < MIN_REFRESH_AGE_HOURS:
        return refresh_status(database_url)
    token = uuid4().hex
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE forecast_refresh_state
            SET state = 'running', started_at = now(), finished_at = NULL,
                next_attempt_at = now() + interval '2 minutes',
                heartbeat_at = now(), run_token = %s, detail = NULL
            WHERE id = 1 AND (
                (state <> 'running' AND next_attempt_at <= now())
                OR (state = 'running' AND (
                    heartbeat_at < now() - interval '2 minutes'
                    OR (heartbeat_at IS NULL AND started_at < now() - interval '2 minutes')
                ))
            )
            RETURNING id
            """,
            (token,),
        )
        claimed = cursor.fetchone() is not None
    if claimed:
        Thread(target=_run, args=(database_url, token), name="forecast-refresh", daemon=True).start()
    return refresh_status(database_url)


def start_uploaded(database_url: str, run_time: datetime, output_dir: Path) -> dict[str, Any]:
    """Claim a trusted, pre-fetched run without requesting Open-Meteo from Render."""
    token = uuid4().hex
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """UPDATE forecast_refresh_state
               SET state = 'running', started_at = now(), finished_at = NULL,
                   next_attempt_at = now() + interval '2 minutes',
                   heartbeat_at = now(), run_token = %s, detail = NULL
               WHERE id = 1 AND (state <> 'running' OR heartbeat_at < now() - interval '2 minutes'
                   OR (heartbeat_at IS NULL AND started_at < now() - interval '2 minutes'))
               RETURNING id""",
            (token,),
        )
        claimed = cursor.fetchone() is not None
    if not claimed:
        shutil.rmtree(output_dir)
        return refresh_status(database_url)
    Thread(
        target=_run, args=(database_url, token, run_time, output_dir),
        name="forecast-upload", daemon=True,
    ).start()
    return refresh_status(database_url)


def _heartbeat(database_url: str, token: str, stop: Event) -> None:
    while not stop.wait(30):
        try:
            with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE forecast_refresh_state SET heartbeat_at = now(),
                       next_attempt_at = now() + interval '2 minutes'
                       WHERE id = 1 AND state = 'running' AND run_token = %s""",
                    (token,),
                )
                if cursor.rowcount == 0:
                    return
        except Exception:
            LOG.exception("Could not renew forecast refresh lease")


def _run(database_url: str, token: str, run_time: datetime | None = None, output_dir: Path | None = None) -> None:
    """Run the existing QC pipeline; preserve the alert block if it fails."""
    from pipeline.operational import run_operational

    stop = Event()
    heartbeat = Thread(target=_heartbeat, args=(database_url, token, stop), name="forecast-heartbeat", daemon=True)
    heartbeat.start()
    try:
        if run_time is None or output_dir is None:
            succeeded = run_operational(database_url)
        else:
            succeeded = run_operational(database_url, run_time=run_time, output_dir=output_dir)
        detail = None if succeeded else "Upstream retrieval or quality checks failed."
    except Exception:
        LOG.exception("Automatic forecast refresh failed")
        succeeded = False
        detail = "The forecast processor failed before completion."
    finally:
        stop.set()
        heartbeat.join(timeout=1)
        if output_dir is not None:
            shutil.rmtree(output_dir, ignore_errors=True)
    try:
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE forecast_refresh_state
                SET state = %s, finished_at = %s,
                    next_attempt_at = now() + (%s * interval '1 minute'), detail = %s
                WHERE id = 1 AND run_token = %s
                """,
                ("succeeded" if succeeded else "failed", datetime.now(UTC), 360 if succeeded else 20, detail, token),
            )
    except Exception:
        LOG.exception("Could not persist forecast refresh status")
