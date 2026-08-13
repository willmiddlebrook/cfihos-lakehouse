import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TUTORIAL = ROOT / "tutorial"
SOURCES = ROOT / "src" / "conform" / "sources"


def _rows(name: str) -> list[dict[str, str]]:
    with (TUTORIAL / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _source(name: str) -> dict[str, object]:
    loaded = yaml.safe_load((SOURCES / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_demo_contract_keys_and_value_maps_match_the_walkthrough() -> None:
    plants = _source("demo_plants.yml")
    units = _source("demo_process_units.yml")
    tags = _source("demo_tags.yml")

    assert plants["key"] == ["plant_code"]
    assert units["key"] == ["plant_code", "process_unit_code"]
    assert tags["key"] == ["plant_code", "tag_name"]
    assert tags["value_maps"] == {
        "tag_class_name": {
            "SEP": "separator",
            "KOD": "knock out drum",
            "PT": "pressure transmitter",
            "PUMP_C": "centrifugal pump",
            "CV": "control valve",
            "FT": "flow transmitter",
        },
        "tag_status": {"IN_SVC": "in operation", "STANDBY": "standby"},
        "production_critical_item_indicator": {"Y": "true", "N": "false"},
        "safety_critical_item_indicator": {"Y": "true", "N": "false"},
    }


def test_demo_csvs_have_six_valid_tags_and_only_two_planted_defects() -> None:
    plants = _rows("demo_plants.csv")
    units = _rows("demo_process_units.csv")
    tags = _rows("demo_tags.csv")
    class_map = _source("demo_tags.yml")["value_maps"]["tag_class_name"]

    valid = [
        row
        for row in tags
        if row["process_unit_code"] and row["tag_class_code"] in class_map
    ]
    invalid = {row["tag_name"]: row for row in tags if row not in valid}

    assert len(plants) == 1
    assert plants[0]["plant_name"] == "Compressor Station 4"
    assert [row["process_unit_code"] for row in units] == ["U-100", "U-200"]
    assert len(tags) == 8
    assert len(valid) == 6
    assert set(invalid) == {"T-007", "T-008"}
    assert invalid["T-007"]["process_unit_code"] == ""
    assert invalid["T-007"]["tag_class_code"] == "FT"
    assert invalid["T-008"]["process_unit_code"] == "U-200"
    assert invalid["T-008"]["tag_class_code"] == "WIDGET"
