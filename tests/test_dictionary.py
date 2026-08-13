from pathlib import Path

import yaml

from src.parse_dictionary import parse_dictionary

ROOT = Path(__file__).resolve().parents[1]


def test_official_dictionary_parses_without_exceptions() -> None:
    model, exceptions = parse_dictionary(ROOT / "spec" / "C-DM-002-Data-Dictionary-V2.0.xlsx")
    assert exceptions == []
    assert len(model["entities"]) == 139
    assert sum(len(entity["attributes"]) for entity in model["entities"].values()) == 664


def test_verbatim_definition_and_relationship_cardinality_are_preserved() -> None:
    model = yaml.safe_load((ROOT / "model" / "model.yml").read_text(encoding="utf-8"))
    plant_name = next(
        item for item in model["entities"]["plant"]["attributes"] if item["name"] == "plant_name"
    )
    assert plant_name["definition"] == "The full name of the plant"
    assert all(
        relationship["cardinality"]["parent_to_child"]
        and relationship["cardinality"]["child_to_parent"]
        for relationship in model["relationships"]
    )


def test_model_source_hash_is_pinned() -> None:
    model = yaml.safe_load((ROOT / "model" / "model.yml").read_text(encoding="utf-8"))
    assert (
        model["metadata"]["source_sha256"]
        == "65262c62aec49e3a70225d8add4d9658d98a1dd5e18082c6155e94f3ec0db5a1"
    )
