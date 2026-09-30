"""Natural-language query interface over dashboard data (read-only)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import json
import re

from app.repository import data_status, fetch_rows


@dataclass(frozen=True)
class QueryResult:
    """Result of a natural-language query."""

    answer: str
    data: dict | list | None = None
    query_type: str = "unknown"


def _database_url() -> str:
    import os
    return os.environ["DATABASE_URL"]


def find_district(text: str) -> str | None:
    """Return the configured district id named in the text (by id or name), if any."""
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    for row in fetch_rows(_database_url(), "SELECT id, name FROM districts"):
        names = {row["id"].replace("-", " "), re.sub(r"\(.*?\)", "", row["name"].lower()).strip()}
        if any(re.search(rf"\b{re.escape(name)}\b", text) for name in names if name):
            return row["id"]
    return None


def _parse_query(query: str) -> tuple[str, dict]:
    """
    Parse natural language query into intent and parameters.

    Returns:
        (query_type, parameters)
    """
    q = query.lower().strip()
    district = find_district(q)

    # Alert level queries
    if re.search(r"alert.*level|what.*alert|current.*alert", q):
        return "current_alert", {"district_id": district}

    # Temperature queries
    if re.search(r"temperature|temp|how.*hot|max.*temp|tmax", q):
        return "forecast_temperature", {"district_id": district}

    # Thermal index queries
    if re.search(r"utci|wbgt|heat.*index|thermal.*stress", q):
        return "thermal_indices", {"district_id": district}

    # Advisory queries
    if re.search(r"advisory|warning|dispatch", q):
        return "advisory_status", {"district_id": district}

    # Vulnerability queries
    if re.search(r"vulnerab|population|ward|exposure", q):
        return "vulnerability", {"district_id": district}

    # Ranking across districts
    if re.search(r"highest|most at risk|worst|hottest|riskiest|which district|top district", q):
        return "top_risk", {}

    # Data freshness
    if re.search(r"fresh|stale|data.*age|how.*old|current.*data", q):
        return "data_freshness", {}

    # District list
    if re.search(r"district|city|location", q):
        return "district_list", {}

    return "unknown", {"raw_query": query}


def _c(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}°C"


def execute_query(query_type: str, params: dict) -> QueryResult:
    """Execute a parsed query and return structured result."""
    db_url = _database_url()
    if "district_id" in params and params["district_id"] is None:
        return QueryResult(
            answer="Which district? Name one of the monitored districts (e.g. 'alert for Jaipur').",
            data=None,
            query_type=query_type,
        )

    if query_type == "current_alert":
        district_id = params["district_id"]
        rows = fetch_rows(
            db_url,
            """
            SELECT forecast_date AS date, level, track1_level, track2_level,
                   disagreement, reasoning, issued_at
            FROM alerts WHERE district_id = %s
              AND run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
            ORDER BY forecast_date LIMIT 1
            """,
            (district_id,),
        )
        if not rows:
            return QueryResult(
                answer=f"No current alert data for {district_id}",
                data={"district_id": district_id, "alerts": []},
                query_type=query_type,
            )
        alert = rows[0]
        return QueryResult(
            answer=f"{district_id}: {alert['level'].upper()} alert for {alert['date']} (Track 1: {alert['track1_level']}, Track 2: {alert['track2_level']})",
            data=alert,
            query_type=query_type,
        )

    elif query_type == "forecast_temperature":
        district_id = params["district_id"]
        rows = fetch_rows(
            db_url,
            """
            SELECT forecast_date AS date, tmax_c, tmin_c
            FROM forecast_daily WHERE district_id = %s
              AND run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
            ORDER BY forecast_date LIMIT 3
            """,
            (district_id,),
        )
        if not rows:
            return QueryResult(
                answer=f"No forecast data for {district_id}",
                data={"district_id": district_id, "forecast": []},
                query_type=query_type,
            )
        lines = [f"{r['date']}: max {r['tmax_c']:.1f}°C, min {r['tmin_c']:.1f}°C" for r in rows]
        return QueryResult(
            answer=f"{district_id} forecast: " + "; ".join(lines),
            data={"district_id": district_id, "forecast": rows},
            query_type=query_type,
        )

    elif query_type == "thermal_indices":
        district_id = params["district_id"]
        rows = fetch_rows(
            db_url,
            """
            SELECT forecast_date AS date, utci_c, wbgt_est_c, heat_index_c
            FROM thermal_indices WHERE district_id = %s
              AND run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
            ORDER BY forecast_date LIMIT 3
            """,
            (district_id,),
        )
        if not rows:
            return QueryResult(
                answer=f"No thermal indices for {district_id}",
                data={"district_id": district_id, "indices": []},
                query_type=query_type,
            )
        lines = [
            f"{r['date']}: UTCI={_c(r['utci_c'])}, WBGT={_c(r['wbgt_est_c'])}, HI={_c(r['heat_index_c'])}"
            for r in rows
        ]
        return QueryResult(
            answer=f"{district_id} thermal indices: " + "; ".join(lines),
            data={"district_id": district_id, "indices": rows},
            query_type=query_type,
        )

    elif query_type == "advisory_status":
        district_id = params["district_id"]
        today = datetime.now(UTC).date().isoformat()
        rows = fetch_rows(
            db_url,
            """
            SELECT advisory_id, forecast_date, language, alert_level, status, text
            FROM advisory_drafts WHERE district_id = %s
              AND run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
            ORDER BY forecast_date
            """,
            (district_id,),
        )
        if not rows:
            return QueryResult(
                answer=f"No advisories for {district_id}",
                data={"district_id": district_id, "advisories": []},
                query_type=query_type,
            )
        lines = [f"{r['forecast_date']} ({r['language']}): {r['alert_level']} - {r['status']}" for r in rows]
        return QueryResult(
            answer=f"{district_id} advisories: " + "; ".join(lines),
            data={"district_id": district_id, "advisories": rows},
            query_type=query_type,
        )

    elif query_type == "vulnerability":
        district_id = params["district_id"]
        rows = fetch_rows(
            db_url,
            """
            SELECT ward_id, name, population_estimate, data_vintage
            FROM vulnerability_wards WHERE district_id = %s
            ORDER BY population_estimate DESC LIMIT 5
            """,
            (district_id,),
        )
        if not rows:
            return QueryResult(
                answer=f"No vulnerability data for {district_id}",
                data={"district_id": district_id, "wards": []},
                query_type=query_type,
            )
        lines = [f"{r['name']}: {r['population_estimate']:.0f} people ({r['data_vintage']})" for r in rows]
        return QueryResult(
            answer=f"Top 5 wards in {district_id}: " + "; ".join(lines),
            data={"district_id": district_id, "wards": rows},
            query_type=query_type,
        )

    elif query_type == "top_risk":
        rows = fetch_rows(
            db_url,
            """
            SELECT d.name, a.level, t.utci_c, f.tmax_c, a.forecast_date AS date
            FROM alerts a
            JOIN districts d ON d.id = a.district_id
            JOIN thermal_indices t USING (district_id, forecast_date, run_id)
            JOIN forecast_daily f USING (district_id, forecast_date, run_id)
            WHERE a.run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1)
              AND a.forecast_date = (SELECT min(forecast_date) FROM alerts
                  WHERE run_id = (SELECT run_id FROM model_runs ORDER BY init_time DESC LIMIT 1))
            ORDER BY array_position(ARRAY['red','orange','yellow','green'], a.level), t.utci_c DESC
            LIMIT 5
            """,
        )
        if data_status(db_url)["state"] != "current" or not rows:
            return QueryResult(answer="Alerts are blocked or unavailable right now.", data=None, query_type=query_type)
        lines = [f"{r['name']} {r['level'].upper()} (Tmax {_c(r['tmax_c'])}, UTCI {_c(r['utci_c'])})" for r in rows]
        return QueryResult(
            answer=f"Highest risk on {rows[0]['date']}: " + "; ".join(lines),
            data={"districts": rows},
            query_type=query_type,
        )

    elif query_type == "data_freshness":
        status = data_status(db_url)
        return QueryResult(
            answer=f"Data status: {status['state']}. {status['banner']}",
            data=status,
            query_type=query_type,
        )

    elif query_type == "district_list":
        rows = fetch_rows(
            db_url,
            "SELECT id, name, state, climate_zone FROM districts ORDER BY name",
        )
        lines = [f"{r['name']} ({r['state']}) - {r['climate_zone']}" for r in rows]
        return QueryResult(
            answer="Districts: " + "; ".join(lines),
            data={"districts": rows},
            query_type=query_type,
        )

    else:
        return QueryResult(
            answer="I don't understand that query. Try asking about alerts, temperatures, thermal indices, advisories, vulnerability, or data freshness for a district.",
            data={"raw_query": params.get("raw_query", "")},
            query_type="unknown",
        )


INTENTS = (
    "current_alert", "forecast_temperature", "thermal_indices", "advisory_status",
    "vulnerability", "top_risk", "data_freshness", "district_list",
)


def _parse_with_llm(query: str) -> tuple[str, dict] | None:
    """Let the LLM pick the intent and district; answers still come from the database."""
    from app.llm import chat

    districts = fetch_rows(_database_url(), "SELECT id, name FROM districts ORDER BY id")
    reply = chat(
        "Map a question about an Indian heat early-warning dashboard to JSON "
        '{"intent": one of ' + ", ".join(INTENTS) + ', "district_id": one of the ids or null}. '
        "Districts: " + "; ".join(f"{row['id']}={row['name']}" for row in districts) + ". "
        "Use top_risk for questions comparing or ranking districts. Reply with JSON only.",
        query,
        json_mode=True,
    )
    try:
        parsed = json.loads(reply or "")
    except ValueError:
        return None
    intent, district_id = parsed.get("intent"), parsed.get("district_id")
    if intent not in INTENTS or district_id not in {None, *(row["id"] for row in districts)}:
        return None
    needs_district = intent in {"current_alert", "forecast_temperature", "thermal_indices", "advisory_status", "vulnerability"}
    return intent, ({"district_id": district_id} if needs_district else {})


def process_nl_query(query: str) -> QueryResult:
    """Process a natural language query end-to-end (LLM intent parsing, regex fallback)."""
    query_type, params = _parse_with_llm(query) or _parse_query(query)
    return execute_query(query_type, params)


if __name__ == "__main__":
    import os
    os.environ["DATABASE_URL"] = "postgresql://heatwave:heatwave@localhost:5432/heatwave"

    test_queries = [
        "What is the current alert for Ahmedabad?",
        "Show me the temperature forecast for New Delhi",
        "What are the thermal indices for Chennai?",
        "Any advisories for Ahmedabad?",
        "Which wards are most vulnerable in Ahmedabad?",
        "Is the data fresh?",
        "List all districts",
    ]

    for q in test_queries:
        result = process_nl_query(q)
        print(f"Q: {q}")
        print(f"A: {result.answer}")
        print(f"Type: {result.query_type}")
        print("---")