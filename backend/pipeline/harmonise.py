"""Common-grid weather-field harmonisation and hard QC gates."""

import shutil
from pathlib import Path

import numpy as np
import xarray as xr


class QualityControlError(ValueError):
    """Raised when source weather data are unsafe for alert generation."""


ALIASES = {
    "temperature": ("t2m", "2m_temperature"),
    "dewpoint": ("d2m", "2m_dewpoint_temperature"),
    "u_wind": ("u10", "10m_u_component_of_wind"),
    "v_wind": ("v10", "10m_v_component_of_wind"),
    "pressure": ("sp", "surface_pressure"),
    "shortwave": ("ssrd", "surface_solar_radiation_downwards"),
}


def _field(dataset: xr.Dataset, logical_name: str) -> xr.DataArray:
    for name in ALIASES[logical_name]:
        if name in dataset:
            return dataset[name]
    raise QualityControlError(f"missing required field: {logical_name}")


def _temperature_c(field: xr.DataArray) -> xr.DataArray:
    units = field.attrs.get("units")
    if units in {"K", "kelvin"}:
        return field - 273.15
    if units in {"°C", "degC", "C"}:
        return field
    raise QualityControlError(f"unsupported temperature unit: {units!r}")


def _pressure_pa(field: xr.DataArray) -> xr.DataArray:
    units = field.attrs.get("units")
    if units == "Pa":
        return field
    if units in {"hPa", "mbar"}:
        return field * 100
    raise QualityControlError(f"unsupported pressure unit: {units!r}")


def _shortwave_w_m2(field: xr.DataArray) -> xr.DataArray:
    units = field.attrs.get("units")
    if units in {"W m-2", "W m**-2"}:
        return field
    if units in {"J m-2", "J m**-2"}:
        seconds = field.attrs.get("accumulation_seconds")
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            raise QualityControlError("accumulated radiation needs positive accumulation_seconds")
        return field / seconds
    raise QualityControlError(f"unsupported radiation unit: {units!r}")


def _check_range(name: str, field: xr.DataArray, low: float, high: float) -> None:
    values = np.asarray(field.values)
    if not np.isfinite(values).all() or (values < low).any() or (values > high).any():
        raise QualityControlError(f"{name} outside [{low}, {high}] or missing")


def harmonise_dataset(dataset: xr.Dataset) -> xr.Dataset:
    """Convert an hourly ECMWF/ERA5 dataset to audited SI-derived fields in UTC."""
    if "valid_time" in dataset.coords and "time" not in dataset.coords:
        dataset = dataset.rename({"valid_time": "time"})
    if "time" not in dataset.coords:
        raise QualityControlError("missing time coordinate")
    times = np.asarray(dataset.time.values).astype("datetime64[s]")
    if times.size == 0 or (times[1:] <= times[:-1]).any():
        raise QualityControlError("time must be non-empty and strictly increasing")
    if times.size > 1 and (np.diff(times).astype("timedelta64[s]").astype(int) != 3600).any():
        raise QualityControlError("time axis contains hourly gaps")

    temperature = _temperature_c(_field(dataset, "temperature"))
    dewpoint = _temperature_c(_field(dataset, "dewpoint"))
    u_wind = _field(dataset, "u_wind")
    v_wind = _field(dataset, "v_wind")
    if u_wind.attrs.get("units") not in {"m s-1", "m s**-1", "m/s"}:
        raise QualityControlError("unsupported wind unit")
    if v_wind.attrs.get("units") not in {"m s-1", "m s**-1", "m/s"}:
        raise QualityControlError("unsupported wind unit")

    expected_dims = temperature.dims
    fields = (dewpoint, u_wind, v_wind, _field(dataset, "pressure"), _field(dataset, "shortwave"))
    if any(field.dims != expected_dims or field.shape != temperature.shape for field in fields):
        raise QualityControlError("required fields do not share one grid")

    relative_humidity = 100 * np.exp(
        17.625 * dewpoint / (243.04 + dewpoint) - 17.625 * temperature / (243.04 + temperature)
    )
    result = xr.Dataset(
        {
            "temperature_c": temperature,
            "relative_humidity_pct": relative_humidity,
            "wind_speed_m_s": np.hypot(u_wind, v_wind),
            "surface_pressure_pa": _pressure_pa(_field(dataset, "pressure")),
            "shortwave_w_m2": _shortwave_w_m2(_field(dataset, "shortwave")),
        }
    )
    ranges = {
        "temperature_c": (-90, 65),
        "relative_humidity_pct": (0, 100),
        "wind_speed_m_s": (0, 100),
        "surface_pressure_pa": (50_000, 110_000),
        "shortwave_w_m2": (0, 1_600),
    }
    for name, (low, high) in ranges.items():
        _check_range(name, result[name], low, high)
        result[name].attrs["units"] = {
            "temperature_c": "degC",
            "relative_humidity_pct": "%",
            "wind_speed_m_s": "m s-1",
            "surface_pressure_pa": "Pa",
            "shortwave_w_m2": "W m-2",
        }[name]
    result.time.attrs["timezone"] = "UTC"
    result.attrs.update({"qc_status": "pass", "qc_version": "1"})
    return result


def write_harmonised_zarr(dataset: xr.Dataset, output: str | Path) -> Path:
    """Run QC and atomically write a Zarr store; failed QC writes no product."""
    result = harmonise_dataset(dataset)
    output = Path(output)
    if output.exists():
        return output
    partial = output.with_name(f"{output.name}.part")
    if partial.exists():
        shutil.rmtree(partial)
    try:
        result.to_zarr(partial, mode="w", zarr_format=2)
        partial.replace(output)
    except Exception:
        if partial.exists():
            shutil.rmtree(partial)
        raise
    return output
