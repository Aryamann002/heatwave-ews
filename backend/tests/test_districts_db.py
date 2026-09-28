"""PostGIS seed and spatial-join test for pilot districts."""

import os
import unittest

import psycopg

from app.districts import seed_districts


class DistrictDatabaseTest(unittest.TestCase):
    def test_seeded_points_join_their_district_polygons(self) -> None:
        database_url = os.environ["DATABASE_URL"]
        seed_districts(database_url)
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*)
                FROM districts
                WHERE ST_Covers(geom, ST_SetSRID(ST_MakePoint(longitude, latitude), 4326))
                """
            )
            self.assertEqual(cursor.fetchone()[0], 3)


if __name__ == "__main__":
    unittest.main()
