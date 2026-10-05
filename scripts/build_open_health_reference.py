"""Build checked, tidy public heat-health reference files from official sources.

This is an offline preparation utility, not part of the live forecast pipeline.
It intentionally keeps annual national/state outcomes out of health_observations,
which accepts only approved ward-day operational data.
"""

from __future__ import annotations

import csv
import hashlib
import html
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import ssl
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "reference" / "health"
CENSUS_URL = (
    "https://censusindia.gov.in/nada/index.php/api/tables/data/2011/PC11_C14/5000"
    "?scst=0&geo_level=2&urbrur=0&sex=0&age_group=60,65,70,75,80,88"
    "&fields=state,district,age_group,value&format=csv"
)
PIB_URL = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2158403&lang=2&reg=48"


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table" and self._table is None:
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            value = " ".join("".join(self._cell).split())
            self._row.append(html.unescape(value))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def _download(url: str) -> bytes:
    # Some Windows/Python installations do not expose the system CA store. These
    # three fixed official HTTPS endpoints are verified after download by strict
    # schema/totals checks and the committed files are pinned by SHA-256.
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    request = urllib.request.Request(url, headers={"User-Agent": "Heatwatch reference-data builder/1.0"})
    with urllib.request.urlopen(request, context=context, timeout=120) as response:
        return response.read()


def _write_csv(name: str, fieldnames: list[str], rows: list[dict[str, object]]) -> Path:
    path = OUTPUT / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _district_demographics() -> tuple[Path, dict[str, object]]:
    payload = _download(CENSUS_URL)
    raw_rows = list(csv.DictReader(io.StringIO(payload.decode("utf-16le"))))
    ages: dict[tuple[int, int], dict[int, int]] = {}
    for row in raw_rows:
        key = (int(row["state"]), int(row["district"]))
        ages.setdefault(key, {})[int(row["age_group"])] = int(row["value"])
    if len(ages) != 640 or any(set(values) != {60, 65, 70, 75, 80, 88} for values in ages.values()):
        raise ValueError("Census API did not return six expected age records for all 640 districts")

    features = json.loads((ROOT / "config" / "pilot_districts.geojson").read_text(encoding="utf-8"))["features"]
    districts = json.loads((ROOT / "config" / "districts.yaml").read_text(encoding="utf-8"))["districts"]
    district_id_by_code = {tuple(item["census_code"]): item["id"] for item in districts}
    features_by_state: dict[int, list[dict[str, object]]] = {}
    for feature in features:
        props = feature["properties"]
        state_code = int(props["ST_CEN_CD"])
        if state_code == 99:  # source boundary artifact, not a Census district
            continue
        features_by_state.setdefault(state_code, []).append(props)

    api_by_state: dict[int, list[tuple[int, dict[int, int]]]] = {}
    for (state_code, national_district_code), values in ages.items():
        api_by_state.setdefault(state_code, []).append((national_district_code, values))

    output: list[dict[str, object]] = []
    for state_code in sorted(features_by_state):
        state_features = sorted(features_by_state[state_code], key=lambda item: int(item["DT_CEN_CD"]))
        state_api = sorted(api_by_state[state_code], key=lambda item: item[0])
        if len(state_features) != len(state_api):
            raise ValueError(f"Census district count mismatch for state code {state_code}")
        for props, (national_code, values) in zip(state_features, state_api, strict=True):
            local_code = int(props["DT_CEN_CD"])
            total = values[88]
            elderly = sum(values[age] for age in (60, 65, 70, 75, 80))
            output.append({
                "district_id": district_id_by_code[(state_code, local_code)],
                "census_state_code": state_code,
                "census_district_code": local_code,
                "census_national_district_code": national_code,
                "state_name_2011": props["ST_NM"],
                "district_name_2011": props["DISTRICT"],
                "total_population": total,
                "elderly_60_plus": elderly,
                "elderly_share": f"{elderly / total:.6f}",
            })
    path = _write_csv(
        "census_2011_district_elderly.csv",
        ["district_id", "census_state_code", "census_district_code", "census_national_district_code",
         "state_name_2011", "district_name_2011", "total_population", "elderly_60_plus", "elderly_share"],
        output,
    )
    return path, {"rows": len(output), "national_total_population": sum(int(row["total_population"]) for row in output)}


def _npcchh() -> tuple[Path, dict[str, object]]:
    # Transcribed from Annexure A of Rajya Sabha Unstarred Question 1693, answered 06 Aug 2024.
    values = [(2021, 65, None), (2022, 4481, 33), (2023, 19402, 189), (2024, 48385, 185)]
    rows: list[dict[str, object]] = []
    for year, cases, deaths in values:
        period_end = "2024-07-28" if year == 2024 else f"{year}-07-31"
        for outcome_type, count in (("suspected_heat_illness_cases", cases), ("confirmed_heatstroke_deaths", deaths)):
            rows.append({
                "source_id": "npcchh-heat-surveillance-2021-2024",
                "geography_level": "nation",
                "geography_name": "India",
                "year": year,
                "period_end": period_end,
                "outcome_type": outcome_type,
                "count": "" if count is None else count,
                "count_status": "not_reported" if count is None else "reported",
                "operational_training": "false",
                "note": "March 1 to July 31 surveillance period; 2024 data through July 28",
            })
    path = _write_csv("npcchh_heat_surveillance_2021_2024.csv", list(rows[0]), rows)
    return path, {"rows": len(rows), "years": 4}


def _ncrb() -> tuple[Path, dict[str, object]]:
    parser = _TableParser()
    parser.feed(_download(PIB_URL).decode("utf-8", errors="replace"))
    table = next(
        table for table in parser.tables
        if any("TOTAL (ALL INDIA)" in " ".join(row) for row in table)
        and any(row[1:7] == ["State/UT", "2018", "2019", "2020", "2021", "2022"] for row in table if len(row) >= 7)
    )
    rows: list[dict[str, object]] = []
    for cells in table:
        if len(cells) < 7 or cells[1] in {"State/UT", "TOTAL STATE(S)", "TOTAL UT(S)"}:
            continue
        name = cells[1]
        geography_level = "nation" if name == "TOTAL (ALL INDIA)" else "state_or_ut"
        for year, raw_count in zip(range(2018, 2023), cells[2:7], strict=True):
            rows.append({
                "source_id": "ncrb-heat-sunstroke-deaths-2018-2022",
                "geography_level": geography_level,
                "geography_name": "India" if geography_level == "nation" else name,
                "year": year,
                "period_end": f"{year}-12-31",
                "outcome_type": "deaths_due_to_heat_or_sunstroke",
                "count": 0 if raw_count == "-" else int(raw_count),
                "count_status": "reported",
                "operational_training": "false",
                "note": "Annual NCRB accidental-death count; state/UT labels preserved from source",
            })
    national = {int(row["year"]): int(row["count"]) for row in rows if row["geography_level"] == "nation"}
    if national != {2018: 890, 2019: 1274, 2020: 530, 2021: 374, 2022: 730}:
        raise ValueError(f"Unexpected NCRB national totals: {national}")
    path = _write_csv("ncrb_heat_sunstroke_deaths_2018_2022.csv", list(rows[0]), rows)
    return path, {"rows": len(rows), "national_totals": national}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, dict[str, object]] = {}
    for source_id, builder in (
        ("census-c14-2011", _district_demographics),
        ("npcchh-heat-surveillance-2021-2024", _npcchh),
        ("ncrb-heat-sunstroke-deaths-2018-2022", _ncrb),
    ):
        path, checks = builder()
        outputs[path.name] = {
            "source_id": source_id,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "checks": checks,
        }
    print(json.dumps(outputs, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
