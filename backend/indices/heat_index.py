"""Rothfusz Heat Index calculation."""

from typing import TypeAlias

import numpy as np
from pythermalcomfort.models import heat_index_rothfusz

NumericInput: TypeAlias = float | int | list[float] | np.ndarray


def calculate_heat_index(
    air_temperature_c: NumericInput,
    relative_humidity_pct: NumericInput,
) -> float | np.ndarray:
    """Return Rothfusz Heat Index in °C for air temperature °C and RH %."""
    result = heat_index_rothfusz(
        tdb=air_temperature_c,
        rh=relative_humidity_pct,
        round_output=True,
        limit_inputs=True,
    ).hi
    return float(result) if np.ndim(result) == 0 else result
