"""Estimated outdoor wet-bulb globe temperature."""

from typing import TypeAlias

import numpy as np
import thermofeel

NumericInput: TypeAlias = float | int | list[float] | np.ndarray


def calculate_wbgt_est(
    air_temperature_c: NumericInput,
    relative_humidity_pct: NumericInput,
    surface_pressure_hpa: NumericInput,
    wind_speed_10m_m_s: NumericInput,
    shortwave_radiation_w_m2: NumericInput,
    direct_radiation_fraction: NumericInput,
    cosine_solar_zenith: NumericInput,
) -> float | np.ndarray:
    """Return estimated outdoor WBGT in °C from forecast meteorology.

    Inputs are °C, %, hPa, m/s at 10 m, W/m², fraction [0, 1], and cosine
    of solar zenith [-1, 1]. The Liljegren calculation is provided by
    thermofeel 2.3.0 and returns Kelvin, converted here to °C.
    """
    rh = np.asarray(relative_humidity_pct, dtype=float)
    pressure = np.asarray(surface_pressure_hpa, dtype=float)
    wind = np.asarray(wind_speed_10m_m_s, dtype=float)
    radiation = np.asarray(shortwave_radiation_w_m2, dtype=float)
    direct_fraction = np.asarray(direct_radiation_fraction, dtype=float)
    cos_zenith = np.asarray(cosine_solar_zenith, dtype=float)

    checks = (
        (np.any((rh < 0) | (rh > 100)), "relative humidity must be in [0, 100]%"),
        (np.any(pressure <= 0), "surface pressure must be positive"),
        (np.any(wind < 0), "wind speed must be non-negative"),
        (np.any(radiation < 0), "shortwave radiation must be non-negative"),
        (
            np.any((direct_fraction < 0) | (direct_fraction > 1)),
            "direct radiation fraction must be in [0, 1]",
        ),
        (
            np.any((cos_zenith < -1) | (cos_zenith > 1)),
            "cosine solar zenith must be in [-1, 1]",
        ),
    )
    for invalid, message in checks:
        if invalid:
            raise ValueError(message)

    result = thermofeel.calculate_wbgt_liljegren(
        np.asarray(air_temperature_c, dtype=float) + 273.15,
        rh,
        pressure,
        wind,
        radiation,
        direct_fraction,
        cos_zenith,
    ) - 273.15
    return float(result) if np.ndim(result) == 0 else result
