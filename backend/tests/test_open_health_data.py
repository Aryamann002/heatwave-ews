"""Public heat-health reference data validation tests."""

import csv
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.open_health_data import DATA_DIR, MANIFEST_PATH, validate_reference_files


class OpenHealthDataTest(unittest.TestCase):
    def test_committed_reference_files_pass_control_totals(self) -> None:
        summary = validate_reference_files()
        self.assertEqual(summary["district_demographic_rows"], 640)
        self.assertEqual(summary["outcome_reference_rows"], 193)
        self.assertEqual(len(summary["source_ids"]), 3)

    def test_missing_npcchh_2021_death_count_is_not_converted_to_zero(self) -> None:
        with (DATA_DIR / "npcchh_heat_surveillance_2021_2024.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        row = next(
            item for item in rows
            if item["year"] == "2021" and item["outcome_type"] == "confirmed_heatstroke_deaths"
        )
        self.assertEqual(row["count"], "")
        self.assertEqual(row["count_status"], "not_reported")
        self.assertEqual(row["operational_training"], "false")

    def test_checksum_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_dir = Path(temp)
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            for source in manifest["sources"]:
                payload = (DATA_DIR / source["file"]).read_bytes()
                (temp_dir / source["file"]).write_bytes(payload)
            tampered = temp_dir / manifest["sources"][0]["file"]
            tampered.write_bytes(tampered.read_bytes() + b"\n")
            manifest_path = temp_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                validate_reference_files(manifest_path, temp_dir)


if __name__ == "__main__":
    unittest.main()
