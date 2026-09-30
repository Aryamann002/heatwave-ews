"""Minimal live forecast harmonisation used by the Phase 1 dashboard."""

import math
import hashlib
import json
import os
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg

from app.alerts import classify_track1_day, combine_tracks, evaluate_track1, evaluate_track2
from app.repository import ensure_operational_tables
from app.districts import seed_districts
from indices.heat_index import calculate_heat_index
from indices.utci import calculate_utci
from indices.wbgt_est import calculate_wbgt_est
from models.baselines import raw_forecast_imd_baseline
from models.train_bias import features as bias_features, load_correctors
from pipeline.climatology import load_normals
from pipeline.s1_fetch import HOURLY_FIELDS, fetch_open_meteo, load_districts


def solar_zenith_cosine(timestamp: datetime, latitude: float, longitude: float) -> float:
    """Return unitless solar-zenith cosine using NOAA's approximate equations."""
    timestamp = timestamp.astimezone(UTC)
    days = 366 if timestamp.year % 4 == 0 else 365
    hour = timestamp.hour + timestamp.minute / 60 + timestamp.second / 3600
    gamma = 2 * math.pi / days * (timestamp.timetuple().tm_yday - 1 + (hour - 12) / 24)
    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    hour_angle = math.radians(((hour * 60 + equation_of_time + 4 * longitude) / 4) - 180)
    latitude_radians = math.radians(latitude)
    return max(
        -1.0,
        min(
            1.0,
            math.sin(latitude_radians) * math.sin(declination)
            + math.cos(latitude_radians) * math.cos(declination) * math.cos(hour_angle),
        ),
    )


def harmonise_district_forecast(
    document: dict[str, Any], latitude: float, longitude: float
) -> list[dict[str, Any]]:
    """QC hourly Open-Meteo SI fields and aggregate hottest-hour daily indices."""
    hourly = document.get("hourly", {})
    required = ("time", *HOURLY_FIELDS)
    if any(name not in hourly for name in required):
        raise ValueError("forecast is missing a required hourly field")
    length = len(hourly["time"])
    if length == 0 or any(len(hourly[name]) != length for name in required):
        raise ValueError("hourly fields must be non-empty and equally sized")
    if any(value < 0 or value > 100 for value in hourly["relative_humidity_2m"]):
        raise ValueError("relative humidity failed QC")
    if any(value < 0 for value in hourly["wind_speed_10m"]):
        raise ValueError("wind speed failed QC")
    if any(value <= 0 for value in hourly["surface_pressure"]):
        raise ValueError("surface pressure failed QC")
    if any(value < 0 for name in ("shortwave_radiation", "direct_radiation") for value in hourly[name]):
        raise ValueError("radiation failed QC")

    grouped: dict[date, list[int]] = {}
    # Times are local to the requested timezone; Open-Meteo reports its offset.
    local = timezone(timedelta(seconds=document.get("utc_offset_seconds", 0)))
    timestamps = [datetime.fromisoformat(value).replace(tzinfo=local) for value in hourly["time"]]
    for index, timestamp in enumerate(timestamps):
        grouped.setdefault(timestamp.date(), []).append(index)

    days = []
    for forecast_date, indexes in grouped.items():
        hottest = max(indexes, key=lambda index: hourly["temperature_2m"][index])
        temperature = float(hourly["temperature_2m"][hottest])
        humidity = float(hourly["relative_humidity_2m"][hottest])
        wind = float(hourly["wind_speed_10m"][hottest])
        shortwave = float(hourly["shortwave_radiation"][hottest])
        direct = float(hourly["direct_radiation"][hottest])
        if direct > shortwave and shortwave > 0:
            raise ValueError("direct radiation exceeds global shortwave radiation")
        direct_fraction = direct / shortwave if shortwave else 0.0
        cosine = solar_zenith_cosine(timestamps[hottest], latitude, longitude)
        days.append(
            {
                "date": forecast_date,
                "tmax_c": temperature,
                "tmin_c": min(float(hourly["temperature_2m"][index]) for index in indexes),
                "relative_humidity_pct": humidity,
                "wind_speed_m_s": wind,
                # Phase 1 UTCI is explicitly a shade estimate (MRT = air temperature).
                "utci_c": calculate_utci(temperature, temperature, max(wind, 0.5), humidity),
                "wbgt_est_c": calculate_wbgt_est(
                    temperature,
                    humidity,
                    float(hourly["surface_pressure"][hottest]),
                    wind,
                    shortwave,
                    direct_fraction,
                    cosine,
                ),
                "heat_index_c": calculate_heat_index(temperature, humidity),
            }
        )
    return days


def consecutive_hot_nights(
    days: list[dict[str, Any]], normals: list[tuple[float, float, float] | None]
) -> list[int]:
    """Running count of consecutive days whose Tmin reaches the 1991-2020 p90 Tmin."""
    counts, run = [], 0
    for day, normal in zip(days, normals, strict=True):
        run = run + 1 if normal is not None and day["tmin_c"] >= normal[2] else 0
        counts.append(run)
    return counts


def evaluate_days(
    climate_zone: str, days: list[dict[str, Any]], normals: list[tuple[float, float, float] | None]
) -> list[tuple[Any, Any, Any, Any]]:
    """Per day: (Track 1 day condition, Track 1, Track 2, combined) -- shared by live and replay."""
    conditions = [
        classify_track1_day(climate_zone, day["tmax_c"], normal[0] if normal else None)
        for day, normal in zip(days, normals, strict=True)
    ]
    hot_nights = consecutive_hot_nights(days, normals)
    results = []
    labels = [item.condition for item in conditions]
    for index, day in enumerate(days):
        # Persistence looks ahead (early warning), and a hot day also keeps the hot run it
        # belongs to, so the last days of a spell are not reset to green for lack of look-ahead.
        start = index
        while start > 0 and labels[start - 1] != "normal" and labels[index] != "normal":
            start -= 1
        track1 = evaluate_track1(labels[start:])
        track2 = evaluate_track2(day["utci_c"], day["wbgt_est_c"], hot_nights[index], None)
        results.append((conditions[index], track1, track2, combine_tracks(track1.level, track2.level)))
    return results


def run_operational(
    database_url: str,
    run_time: datetime | None = None,
    output_dir: str | Path = "data/raw/open-meteo",
) -> bool:
    """Fetch, QC, calculate, alert, and persist one idempotent forecast cycle."""
    now = datetime.now(UTC)
    run_time = run_time or now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0)
    expected_run_id = f"open-meteo-{run_time:%Y%m%dT%H%M%SZ}"
    seed_districts(database_url)
    ensure_operational_tables(database_url)
    try:
        districts = load_districts()
        manifest = fetch_open_meteo(districts, run_time, output_dir)
        run_dir = Path(output_dir) / manifest["run_id"]
        daily_by_district = {}
        for district, file_record in zip(districts, manifest["files"], strict=True):
            document = json.loads((run_dir / file_record["path"]).read_text(encoding="utf-8"))
            daily_by_district[district["id"]] = harmonise_district_forecast(
                document, district["latitude"], district["longitude"]
            )
        checksum = hashlib.sha256(
            "".join(record["sha256"] for record in manifest["files"]).encode()
        ).hexdigest()
    except Exception as error:
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO model_runs VALUES (%s, %s, %s, %s, %s, 'fail', %s)
                ON CONFLICT (run_id) DO UPDATE SET retrieved_at=EXCLUDED.retrieved_at,
                    qc_status='fail', failure_reason=EXCLUDED.failure_reason
                """,
                (expected_run_id, "open-meteo", run_time, now, "unavailable", str(error)),
            )
        return False

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO model_runs VALUES (%s, %s, %s, %s, %s, 'pass', NULL)
            ON CONFLICT (run_id) DO UPDATE SET retrieved_at=EXCLUDED.retrieved_at,
                checksum=EXCLUDED.checksum, qc_status='pass', failure_reason=NULL
            """,
            (
                manifest["run_id"],
                manifest["source"],
                run_time,
                datetime.fromisoformat(manifest["retrieved_at"]),
                checksum,
            ),
        )
        district_by_id = {district["id"]: district for district in districts}
        # Trained, held-out-validated Tmax correction into the ERA5 frame of the normals.
        correctors = load_correctors()
        for district_id, days in daily_by_district.items():
            district = district_by_id[district_id]
            # 1991-2020 normals; empty until pipeline.climatology has loaded this district.
            climatology = load_normals(database_url, district_id)
            normals = [climatology.get(day["date"].timetuple().tm_yday) for day in days]
            corrector = correctors.get(district["climate_zone"])
            for day in days:
                day["raw_tmax_c"] = day["tmax_c"]
                if corrector is not None:
                    day["tmax_c"] = corrector.correct(
                        day["tmax_c"], bias_features(day["tmax_c"], day["date"], district["latitude"])
                    )
            evaluations = evaluate_days(district["climate_zone"], days, normals)
            baseline_predictions = raw_forecast_imd_baseline(
                district["climate_zone"],
                (
                    (day["date"], day["tmax_c"], normal[0] if normal else None)
                    for day, normal in zip(days, normals, strict=True)
                ),
            )
            for day, (condition, track1, track2, combined) in zip(days, evaluations, strict=True):
                heat_index = day["heat_index_c"]
                if isinstance(heat_index, float) and math.isnan(heat_index):
                    heat_index = None
                cursor.execute(
                    """
                    INSERT INTO forecast_daily VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (district_id, forecast_date, run_id) DO UPDATE SET
                        tmax_c=EXCLUDED.tmax_c, tmin_c=EXCLUDED.tmin_c,
                        relative_humidity_pct=EXCLUDED.relative_humidity_pct,
                        wind_speed_m_s=EXCLUDED.wind_speed_m_s
                    """,
                    (
                        district_id, day["date"], manifest["run_id"], day["tmax_c"],
                        day["tmin_c"], day["relative_humidity_pct"], day["wind_speed_m_s"],
                    ),
                )
                cursor.execute(
                    """
                    INSERT INTO thermal_indices VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (district_id, forecast_date, run_id) DO UPDATE SET
                        utci_c=EXCLUDED.utci_c, wbgt_est_c=EXCLUDED.wbgt_est_c,
                        heat_index_c=EXCLUDED.heat_index_c
                    """,
                    (
                        district_id, day["date"], manifest["run_id"], day["utci_c"],
                        day["wbgt_est_c"], heat_index,
                    ),
                )
                reasoning = (
                    condition.reasons + track1.reasons + track2.reasons + combined.reasons
                    + ((f"raw_forecast_tmax={day['raw_tmax_c']:.1f}C (bias-corrected to ERA5)",) if corrector else ())
                )
                cursor.execute(
                    """
                    INSERT INTO alerts VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (district_id, forecast_date, run_id) DO UPDATE SET
                        level=EXCLUDED.level, track1_level=EXCLUDED.track1_level,
                        track2_level=EXCLUDED.track2_level, disagreement=EXCLUDED.disagreement,
                        reasoning=EXCLUDED.reasoning, rule_version=EXCLUDED.rule_version,
                        model_versions=EXCLUDED.model_versions, issued_at=EXCLUDED.issued_at
                    """,
                    (
                        district_id, day["date"], manifest["run_id"], combined.level,
                        track1.level, track2.level, combined.disagreement, json.dumps(reasoning),
                        track1.rule_version,
                        json.dumps({
                            "forecast": "open-meteo",
                            "tmax_bias_correction": "lightgbm-per-zone" if corrector else "none",
                            "classifier": "not_available",
                        }),
                        datetime.now(UTC),
                    ),
                )
            for prediction in baseline_predictions:
                cursor.execute(
                    """
                    INSERT INTO baseline_predictions VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (district_id, forecast_date, run_id, baseline) DO UPDATE SET
                        lead_day=EXCLUDED.lead_day, level=EXCLUDED.level
                    """,
                    (
                        district_id,
                        prediction.target_date,
                        manifest["run_id"],
                        prediction.baseline,
                        prediction.lead_day,
                        prediction.level,
                    ),
                )
    return True


def main() -> None:
    """Run one live cycle; failures are persisted so the UI can show a blocker."""
    run_operational(os.environ["DATABASE_URL"])
