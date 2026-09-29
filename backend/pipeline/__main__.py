"""Operational pipeline command (forecast cycle + one-time ward exposure load)."""

import os
import sys

import psycopg

from pipeline.operational import run_operational


def _scalar(database_url: str, query: str):
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone()
        return row[0] if row else None


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    ok = run_operational(database_url)
    if ok:
        print("forecast run: OK", flush=True)
    else:
        reason = _scalar(
            database_url,
            "SELECT failure_reason FROM model_runs ORDER BY init_time DESC LIMIT 1",
        )
        print(f"forecast run: FAILED - {reason}", file=sys.stderr, flush=True)

    # Ward exposure was never loaded by anything, so the dashboard panel stayed empty.
    try:
        if not _scalar(database_url, "SELECT count(*) FROM vulnerability_wards"):
            from pipeline.vulnerability import main as load_vulnerability

            load_vulnerability()
    except Exception as error:  # non-fatal: forecast alerts must not depend on this
        print(f"vulnerability load skipped: {error}", file=sys.stderr, flush=True)


main()
