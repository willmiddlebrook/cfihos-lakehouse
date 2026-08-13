from copy import deepcopy
from pathlib import Path

import yaml

from src.onramp.engine import (
    match_record,
    process_rows,
    unmapped_exception_id,
    validate_config,
)

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


def test_changed_unmapped_value_gets_distinct_exception_identity() -> None:
    first = unmapped_exception_id("source_a", "record-1", "tag.tag_status", "UNKNOWN")
    second = unmapped_exception_id("source_a", "record-1", "tag.tag_status", "OTHER")
    assert first != second


def test_founding_source_must_claim_every_required_attribute() -> None:
    config, model = load_inputs()
    incomplete = deepcopy(config)
    del incomplete["claims"]["equipment.equipment_class_name"]
    errors = validate_config(incomplete, model)
    assert any(
        "founding feed equipment: missing required claims "
        "equipment.equipment_class_name" in error
        for error in errors
    )


def test_claim_field_must_mirror_the_feed_mapping() -> None:
    config, model = load_inputs()
    invalid = deepcopy(config)
    invalid["claims"]["equipment.equipment_code"]["field"] = "wrong_column"
    errors = validate_config(invalid, model)
    assert any(
        "claim equipment.equipment_code: field must equal feed mapping 'asset_code'" in error
        for error in errors
    )


def test_feed_must_target_a_generated_registry_entity() -> None:
    _, model = load_inputs()
    generated = set(model["generation"]["spine_entities"])
    entity_name = next(name for name in model["entities"] if name not in generated)
    entity = model["entities"][entity_name]
    identifier = next(
        item["name"] for item in entity["attributes"] if item["requirement"] == "identifier"
    )
    config = {
        "source": "out_of_scope_fixture",
        "arrives_as": "table",
        "origination": "steward_only",
        "feeds": {
            entity_name: {
                "from": "fixture_catalog.bronze.out_of_scope_fixture",
                "source_id": "record_id",
                "match_on": [identifier],
                "fields": {identifier: "source_identifier"},
            }
        },
        "claims": {
            f"{entity_name}.{identifier}": {
                "field": "source_identifier",
                "wins_rank": 10,
            }
        },
        "value_maps": {},
        "unmatched": "review_queue",
    }
    errors = validate_config(config, model)
    assert any(
        f"feed {entity_name}: entity is not selected in "
        "model.generation.spine_entities" in error
        for error in errors
    )
