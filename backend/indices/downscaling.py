"""Downscaling: elevation/lapse-rate correction (Ladder rung 2)."""

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class DownscalingConfig:
    """Configuration for elevation-based downscaling."""

    lapse_rate_c_per_km: float = 6.5  # Standard atmospheric lapse rate
    reference_elevation_m: float = 0.0  # Sea level reference
    enabled: bool = True


def load_downscaling_config(path: str | Path = "config/downscaling.yaml") -> DownscalingConfig:
    """Load downscaling configuration from YAML."""
    text = Path(path).read_text(encoding="utf-8")
    # Simple YAML subset parser (JSON-compatible)
    import yaml
    data = yaml.safe_load(text)
    return DownscalingConfig(
        lapse_rate_c_per_km=float(data.get("lapse_rate_c_per_km", 6.5)),
        reference_elevation_m=float(data.get("reference_elevation_m", 0.0)),
        enabled=bool(data.get("enabled", True)),
    )


def apply_elevation_correction(
    temperature_c: float,
    forecast_elevation_m: float,
    target_elevation_m: float,
    config: DownscalingConfig | None = None,
) -> float:
    """
    Correct temperature from forecast grid elevation to target elevation using lapse rate.

    Args:
        temperature_c: Temperature at forecast grid elevation
        forecast_elevation_m: Elevation of the forecast grid point (m)
        target_elevation_m: Elevation of the target location (m)
        config: Downscaling configuration

    Returns:
        Temperature corrected to target elevation
    """
    cfg = config or DownscalingConfig()
    if not cfg.enabled:
        return temperature_c

    elevation_diff_km = (target_elevation_m - forecast_elevation_m) / 1000.0
    correction = -cfg.lapse_rate_c_per_km * elevation_diff_km
    return temperature_c + correction


def get_elevation_for_district(district_id: str, path: str | Path = "config/district_elevations.json") -> float:
    """Get representative elevation for a district (m)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return float(data.get(district_id, 0.0))


def downscale_forecast_for_district(
    forecast_tmax_c: float,
    forecast_tmin_c: float,
    district_id: str,
    forecast_elevation_m: float = 0.0,
    config: DownscalingConfig | None = None,
) -> tuple[float, float]:
    """
    Downscale forecast temperatures to district elevation.

    Returns:
        (downscaled_tmax_c, downscaled_tmin_c)
    """
    target_elevation = get_elevation_for_district(district_id)
    cfg = config or DownscalingConfig()

    if not cfg.enabled or target_elevation == forecast_elevation_m:
        return forecast_tmax_c, forecast_tmin_c

    tmax_downscaled = apply_elevation_correction(
        forecast_tmax_c, forecast_elevation_m, target_elevation, cfg
    )
    tmin_downscaled = apply_elevation_correction(
        forecast_tmin_c, forecast_elevation_m, target_elevation, cfg
    )
    return tmax_downscaled, tmin_downscaled


if __name__ == "__main__":
    # Quick demo
    cfg = DownscalingConfig(lapse_rate_c_per_km=6.5, enabled=True)
    tmax, tmin = downscale_forecast_for_district(40.0, 25.0, "ahmedabad", forecast_elevation_m=50.0, config=cfg)
    print(f"Original: Tmax=40.0°C, Tmin=25.0°C at 50m")
    print(f"Downscaled: Tmax={tmax:.1f}°C, Tmin={tmin:.1f}°C")