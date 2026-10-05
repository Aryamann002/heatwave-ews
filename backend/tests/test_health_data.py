"""Health-data plug-in schema tests."""

import unittest

from pydantic import ValidationError

from models.health_data import HealthObservationBatch


class HealthDataTest(unittest.TestCase):
    def test_accepts_aggregated_ward_day_counts(self) -> None:
        batch = HealthObservationBatch.model_validate({
            "licence_or_agreement": "Municipal data-sharing agreement 2026",
            "observations": [{
                "ward_id": "ward-1", "observation_date": "2026-05-01",
                "outcome_type": "heat_illness_admission", "count": 7,
                "source_name": "City health surveillance", "source_vintage": "2026",
                "aggregation_note": "Daily aggregate at ward level",
            }],
        })
        self.assertEqual(batch.observations[0].count, 7)

    def test_rejects_unexplained_or_duplicate_rows(self) -> None:
        row = {
            "ward_id": "ward-1", "observation_date": "2026-05-01",
            "outcome_type": "all_cause_mortality", "count": 1,
            "source_name": "Registry", "source_vintage": "2026",
            "aggregation_note": "individual record",
        }
        with self.assertRaises(ValidationError):
            HealthObservationBatch.model_validate({"licence_or_agreement": "agreement", "observations": [row]})
