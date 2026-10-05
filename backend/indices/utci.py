"""Universal Thermal Climate Index and solar mean-radiant-temperature helpers."""

import math

from typing import TypeAlias

import numpy as np
from pythermalcomfort.models import solar_gain, utci

NumericInput: TypeAlias = float | int | list[float] | np.ndarray


def calculate_utci(
    air_temperature_c: NumericInput,
    mean_radiant_temperature_c: NumericInput,
    wind_speed_m_s: NumericInput,
    relative_humidity_pct: NumericInput,
) -> float | np.ndarray:
    """Return UTCI in °C for SI inputs (°C, °C, m/s at 10 m, and % RH)."""
    return utci(
        tdb=air_temperature_c,
        tr=mean_radiant_temperature_c,
        v=wind_speed_m_s,
        rh=relative_humidity_pct,
        units="SI",
        limit_inputs=True,
        round_output=True,
    ).utci


def calculate_solar_delta_mrt(
    solar_altitude_deg: float,
    sharp_deg: float,
    direct_normal_radiation_w_m2: float,
    transmittance: float,
    sky_view_fraction: float,
    body_exposure_fraction: float,
) -> float:
    """Return ASHRAE-55 solar delta-MRT in °C for explicit geometry inputs."""
    return float(
        solar_gain(
            sol_altitude=solar_altitude_deg,
            sharp=sharp_deg,
            sol_radiation_dir=direct_normal_radiation_w_m2,
            sol_transmittance=transmittance,
            f_svv=sky_view_fraction,
            f_bes=body_exposure_fraction,
            posture="standing",
            floor_reflectance=0.2,
            round_output=False,
        ).delta_mrt
    )


def calculate_outdoor_mrt(
    air_temperature_c: float,
    direct_horizontal_radiation_w_m2: float,
    solar_zenith_cosine: float,
) -> float:
    """Estimate sun-exposed MRT in °C from direct-horizontal radiation.

    Assumptions: standing person, side-on sun (SHARP 90°), full outdoor
    transmittance, 0.5 sky view, 0.5 body exposure and 0.2 ground reflectance.
    This is an exposure scenario, not a measured globe temperature.
    """
    cosine = max(0.0, min(1.0, solar_zenith_cosine))
    if cosine <= 0.01 or direct_horizontal_radiation_w_m2 <= 0:
        return float(air_temperature_c)
    altitude = math.degrees(math.asin(cosine))
    direct_normal = min(1000.0, max(0.0, direct_horizontal_radiation_w_m2 / cosine))
    if direct_normal <= 0:
        return float(air_temperature_c)
    delta = calculate_solar_delta_mrt(altitude, 90.0, direct_normal, 1.0, 0.5, 0.5)
    return float(air_temperature_c + max(0.0, delta))


def calculate_outdoor_mrt_series(
    air_temperature_c: NumericInput,
    direct_horizontal_radiation_w_m2: NumericInput,
    solar_zenith_cosine: NumericInput,
) -> np.ndarray:
    """Vectorized form of :func:`calculate_outdoor_mrt` for hourly series."""
    air, direct, cosine = np.broadcast_arrays(
        np.asarray(air_temperature_c, dtype=float),
        np.asarray(direct_horizontal_radiation_w_m2, dtype=float),
        np.asarray(solar_zenith_cosine, dtype=float),
    )
    cosine = np.clip(cosine, 0.0, 1.0)
    result = air.copy()
    mask = (cosine > 0.01) & (direct > 0)
    if np.any(mask):
        altitude = np.degrees(np.arcsin(cosine[mask]))
        direct_normal = np.clip(direct[mask] / cosine[mask], 0.0, 1000.0)
        delta = solar_gain(
            sol_altitude=altitude,
            sharp=90.0,
            sol_radiation_dir=direct_normal,
            sol_transmittance=1.0,
            f_svv=0.5,
            f_bes=0.5,
            posture="standing",
            floor_reflectance=0.2,
            round_output=False,
        ).delta_mrt
        result[mask] += np.maximum(0.0, np.asarray(delta, dtype=float))
    return result

