"""Pilot district PostGIS seed loader."""

import json
from pathlib import Path

import psycopg


def seed_districts(
    database_url: str,
    district_path: str | Path = "config/districts.yaml",
    geometry_path: str | Path = "config/pilot_districts.geojson",
) -> None:
    """Idempotently load configured WGS84 district polygons and climate zones."""
    districts = json.loads(Path(district_path).read_text(encoding="utf-8"))["districts"]
    features = json.loads(Path(geometry_path).read_text(encoding="utf-8"))["features"]
    geometry_by_code = {
        int(feature["properties"]["censuscode"]): feature["geometry"]
        for feature in features
    }
    if any(district["boundary_censuscode"] not in geometry_by_code for district in districts):
        raise ValueError("a configured district has no matching boundary geometry")

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS districts (
                id text PRIMARY KEY,
                name text NOT NULL,
                state text NOT NULL,
                climate_zone text NOT NULL,
                latitude double precision NOT NULL,
                longitude double precision NOT NULL,
                boundary_vintage text NOT NULL,
                geom geometry(MultiPolygon, 4326) NOT NULL
            )
            """
        )
        for district in districts:
            geometry = geometry_by_code[district["boundary_censuscode"]]
            cursor.execute(
                """
                INSERT INTO districts
                    (id, name, state, climate_zone, latitude, longitude,
                     boundary_vintage, geom)
                VALUES (%s, %s, %s, %s, %s, %s, 'Census 2011',
                        ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    state = EXCLUDED.state,
                    climate_zone = EXCLUDED.climate_zone,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    boundary_vintage = EXCLUDED.boundary_vintage,
                    geom = EXCLUDED.geom
                """,
                (
                    district["id"],
                    district["name"],
                    district["state"],
                    district["climate_zone"],
                    district["latitude"],
                    district["longitude"],
                    json.dumps(geometry),
                ),
            )
