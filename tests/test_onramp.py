from pathlib import Path

import yaml

from src.onramp.engine import match_record, process_rows, validate_config

ROOT = Path(__file__).resolve().parents[1]


def load_inputs():
    config = yaml.safe_load(
        (ROOT / "src" / "onramp" / "sources" / "example_cmms.yml").read_text(encoding="utf-8")
    )
    model = yaml.safe_load((ROOT / "model" / "model.yml").read_text(encoding="utf-8"))
    return config, model


def test_every_source_yaml_satisfies_the_config_contract() -> None:
    model = load_inputs()[1]
    for path in (ROOT / "src" / "onramp" / "sources").glob("*.yml"):
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert validate_config(config, model) == [], path


def test_match_stops_at_exact_and_uniquely_normalized_tiers() -> None:
    candidates = [
        {"tag_name": "P-100", "spine_id": "one"},
        {"tag_name": "LOC-P-100", "spine_id": "two"},
    ]
    assert match_record({"tag_name": "P-100"}, candidates, ["tag_name"]).tier == "exact"
    ambiguous = match_record(
        {"tag_name": "ASSET-P-100"},
        candidates,
        ["tag_name"],
        ["LOC-", "ASSET-"],
    )
    assert ambiguous.spine_id is None
    assert ambiguous.reason == "multiple normalized candidates"


def test_unmapped_code_is_logged_and_blocked_from_matching() -> None:
    config, _ = load_inputs()
    rows = [
        {
            "location_id": "bad-1",
            "plant_code": "P",
            "functional_location_code": "P-100",
            "description": "fixture",
            "status": "UNKNOWN",
        }
    ]
    candidates = [{"tag_name": "P-100", "spine_id": "one"}]
    result = process_rows(config, "tag", rows, candidates)
    assert len(result["unmapped"]) == 1
    assert result["matched"] == []
    assert result["review"] == []
