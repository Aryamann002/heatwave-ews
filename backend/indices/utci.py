"""Universal Thermal Climate Index calculation."""

from typing import TypeAlias

import numpy as np
from pythermalcomfort.models import utci

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

