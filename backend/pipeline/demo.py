"""Scripted demo scenarios for Phase 5."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.repository import fetch_rows


def load_scenario(name: str) -> dict[str, Any]:
    """Load a demo scenario from stored data."""
    path = Path(f"data/demo/{name}.json")
    if not path.exists():
        raise FileNotFoundError(f"Demo scenario not found: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_demo_scenario(name: str) -> dict[str, Any]:
    """
    Run a scripted demo scenario from stored data (no network).

    Scenarios:
    - normal: typical spring day, green alerts
    - dry-heat: pre-monsoon extreme dry heat, orange/red alerts
    - humid-heat: monsoon-onset humid heat (e.g. April 2023 replay), orange/red alerts
    """
    scenario = load_scenario(name)
    db_url = "postgresql://heatwave:heatwave@localhost:5432/heatwave"

    results = {
        "scenario": name,
        "run_at": datetime.now(UTC).isoformat(),
        "districts": {},
    }

    for district_id in scenario.get("districts", ["ahmedabad", "new-delhi", "chennai"]):
        # Override forecast with scenario data
        forecast = scenario.get("forecast", {}).get(district_id, {})
        indices = scenario.get("indices", {}).get(district_id, {})
        alerts = scenario.get("alerts", {}).get(district_id, {})

        results["districts"][district_id] = {
            "forecast": forecast,
            "indices": indices,
            "alerts": alerts,
        }

    return results


def list_demo_scenarios() -> list[str]:
    """List available demo scenarios."""
    demo_dir = Path("data/demo")
    if not demo_dir.exists():
        return []
    return [p.stem for p in demo_dir.glob("*.json")]


def create_demo_data() -> None:
    """Create default demo scenario files if they don't exist."""
    demo_dir = Path("data/demo")
    demo_dir.mkdir(parents=True, exist_ok=True)

    # Normal day scenario
    normal = {
        "description": "Typical spring day with moderate temperatures",
        "districts": ["ahmedabad", "new-delhi", "chennai"],
        "forecast": {
            "ahmedabad": {
                "2026-03-15": {"tmax_c": 35.0, "tmin_c": 22.0, "rh": 40, "wind": 3.0},
                "2026-03-16": {"tmax_c": 36.0, "tmin_c": 23.0, "rh": 35, "wind": 2.5},
            },
            "new-delhi": {
                "2026-03-15": {"tmax_c": 32.0, "tmin_c": 18.0, "rh": 45, "wind": 2.0},
                "2026-03-16": {"tmax_c": 33.0, "tmin_c": 19.0, "rh": 40, "wind": 2.5},
            },
            "chennai": {
                "2026-03-15": {"tmax_c": 34.0, "tmin_c": 25.0, "rh": 70, "wind": 4.0},
                "2026-03-16": {"tmax_c": 35.0, "tmin_c": 26.0, "rh": 65, "wind": 3.5},
            },
        },
        "indices": {
            "ahmedabad": {"utci_c": 32.0, "wbgt_est_c": 28.0, "heat_index_c": 38.0},
            "new-delhi": {"utci_c": 29.0, "wbgt_est_c": 25.0, "heat_index_c": 34.0},
            "chennai": {"utci_c": 33.0, "wbgt_est_c": 30.0, "heat_index_c": 40.0},
        },
        "alerts": {
            "ahmedabad": {"level": "green", "track1": "green", "track2": "green"},
            "new-delhi": {"level": "green", "track1": "green", "track2": "green"},
            "chennai": {"level": "green", "track1": "green", "track2": "green"},
        },
    }

    # Dry heat scenario (pre-monsoon)
    dry_heat = {
        "description": "Pre-monsoon extreme dry heat event - typical May conditions",
        "districts": ["ahmedabad", "new-delhi", "chennai"],
        "forecast": {
            "ahmedabad": {
                "2026-05-15": {"tmax_c": 46.0, "tmin_c": 30.0, "rh": 15, "wind": 5.0},
                "2026-05-16": {"tmax_c": 47.0, "tmin_c": 31.0, "rh": 12, "wind": 4.0},
                "2026-05-17": {"tmax_c": 45.5, "tmin_c": 29.5, "rh": 18, "wind": 3.5},
            },
            "new-delhi": {
                "2026-05-15": {"tmax_c": 45.0, "tmin_c": 28.0, "rh": 18, "wind": 4.0},
                "2026-05-16": {"tmax_c": 46.5, "tmin_c": 29.0, "rh": 15, "wind": 3.5},
                "2026-05-17": {"tmax_c": 44.0, "tmin_c": 27.5, "rh": 20, "wind": 3.0},
            },
            "chennai": {
                "2026-05-15": {"tmax_c": 40.0, "tmin_c": 29.0, "rh": 50, "wind": 6.0},
                "2026-05-16": {"tmax_c": 41.0, "tmin_c": 30.0, "rh": 45, "wind": 5.5},
            },
        },
        "indices": {
            "ahmedabad": {"utci_c": 42.0, "wbgt_est_c": 32.0, "heat_index_c": 46.0},
            "new-delhi": {"utci_c": 40.0, "wbgt_est_c": 30.0, "heat_index_c": 44.0},
            "chennai": {"utci_c": 38.0, "wbgt_est_c": 33.0, "heat_index_c": 45.0},
        },
        "alerts": {
            "ahmedabad": {"level": "red", "track1": "red", "track2": "red"},
            "new-delhi": {"level": "orange", "track1": "orange", "track2": "red"},
            "chennai": {"level": "orange", "track1": "green", "track2": "orange"},
        },
    }

    # Humid heat scenario (April 2023 replay)
    humid_heat = {
        "description": "April 2023 humid heatwave replay - high humidity with extreme temperatures",
        "districts": ["ahmedabad", "new-delhi", "chennai"],
        "forecast": {
            "ahmedabad": {
                "2023-04-15": {"tmax_c": 43.0, "tmin_c": 28.0, "rh": 65, "wind": 3.0},
                "2023-04-16": {"tmax_c": 44.0, "tmin_c": 29.0, "rh": 70, "wind": 2.5},
                "2023-04-17": {"tmax_c": 42.5, "tmin_c": 27.5, "rh": 68, "wind": 3.5},
            },
            "new-delhi": {
                "2023-04-15": {"tmax_c": 41.0, "tmin_c": 26.0, "rh": 60, "wind": 2.5},
                "2023-04-16": {"tmax_c": 42.0, "tmin_c": 27.0, "rh": 65, "wind": 2.0},
                "2023-04-17": {"tmax_c": 40.5, "tmin_c": 25.5, "rh": 62, "wind": 3.0},
            },
            "chennai": {
                "2023-04-15": {"tmax_c": 39.0, "tmin_c": 28.0, "rh": 80, "wind": 4.0},
                "2023-04-16": {"tmax_c": 39.5, "tmin_c": 28.5, "rh": 82, "wind": 3.5},
            },
        },
        "indices": {
            "ahmedabad": {"utci_c": 45.0, "wbgt_est_c": 35.0, "heat_index_c": 52.0},
            "new-delhi": {"utci_c": 43.0, "wbgt_est_c": 34.0, "heat_index_c": 50.0},
            "chennai": {"utci_c": 41.0, "wbgt_est_c": 36.0, "heat_index_c": 51.0},
        },
        "alerts": {
            "ahmedabad": {"level": "red", "track1": "orange", "track2": "red"},
            "new-delhi": {"level": "red", "track1": "orange", "track2": "red"},
            "chennai": {"level": "red", "track1": "green", "track2": "red"},
        },
    }

    for name, data in [("normal", normal), ("dry-heat", dry_heat), ("humid-heat", humid_heat)]:
        path = demo_dir / f"{name}.json"
        if not path.exists():
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    create_demo_data()
    print("Demo scenarios created:")
    for s in list_demo_scenarios():
        print(f"  - {s}")