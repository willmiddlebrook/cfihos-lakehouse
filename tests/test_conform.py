from datetime import date
from pathlib import Path

import pytest

from src.conform import (
    _prepared_column_name,
    cast_value,
    check_row,
    entity_metadata,
    expected_rdl_tables,
    rdl_value_column,
    validate_config,
    validate_source_config,
)

ROOT = Path(__file__).resolve().parents[1]


def _model() -> dict:
    return {
        "metadata": {"cfihos_version": "2.0"},
        "generation": {
            "spine_entities": ["plant", "process_unit", "tag"],
            "technical_columns": [
                {"name": "spine_id", "datatype": "STRING", "nullable": False}
            ],
        },
        "entities": {
            "plant": {
                "subject_area": "functional_asset",
                "attributes": [
                    {
                        "name": "plant_code",
                        "datatype": "STRING",
                        "requirement": "identifier",
                        "references": "",
                    }
                ],
            },
            "process_unit": {
                "subject_area": "functional_asset",
                "attributes": [
                    {
                        "name": "plant_code",
                        "datatype": "STRING",
                        "requirement": "identifier",
                        "references": "plant",
                    },
                    {
                        "name": "process_unit_code",
                        "datatype": "STRING",
                        "requirement": "identifier",
                        "references": "",
                    },
                ],
            },
            "tag": {
                "subject_area": "functional_asset",
                "attributes": [
                    {
                        "name": "plant_code",
                        "datatype": "STRING",
                        "requirement": "identifier",
                        "references": "",
                    },
                    {
                        "name": "tag_name",
                        "datatype": "STRING",
                        "requirement": "identifier",
                        "references": "",
                    },
                    {
                        "name": "parent_tag_name",
                        "datatype": "STRING",
                        "requirement": "optional",
                        "references": "tag",
                    },
                    {
                        "name": "process_unit_code",
                        "datatype": "STRING",
                        "requirement": "mandatory",
                        "references": "process_unit",
                    },
                    {
                        "name": "tag_class_name",
                        "datatype": "STRING",
                        "requirement": "mandatory",
                        "references": "tag_class",
                    },
                    {
                        "name": "critical_indicator",
                        "datatype": "BOOLEAN",
                        "requirement": "mandatory",
                        "references": "",
                    },
                    {
                        "name": "installed_on",
                        "datatype": "DATE",
                        "requirement": "optional",
                        "references": "",
                    },
                ],
            },
        },
    }


def _tag_config(**updates: object) -> dict:
    payload = {
        "source": "demo_tags",
        "into": "tag",
        "from": "${catalog}.bronze.demo_tags",
        "key": ["plant_code", "tag_name"],
        "fields": {
            "plant_code": "plant",
            "tag_name": "tag",
            "process_unit_code": "unit",
            "tag_class_name": "class_code",
            "critical_indicator": "critical",
        },
        "value_maps": {"tag_class_name": {"SEP": "separator"}},
    }
    payload.update(updates)
    return payload


def test_source_config_is_strict_and_model_driven() -> None:
    config = validate_config(_tag_config(), _model())
    assert config.mode == "upsert"
    assert config.from_table == "${catalog}.bronze.demo_tags"
    assert config.key == ("plant_code", "tag_name")

    with pytest.raises(ValueError, match="unknown top-level source keys: surprise"):
        validate_config(_tag_config(surprise=True), _model())
    with pytest.raises(ValueError, match="tag.not_in_model is not a model attribute"):
        validate_config(
            _tag_config(fields={"plant_code": "plant", "not_in_model": "mystery"}),
            _model(),
        )
    with pytest.raises(ValueError, match="key attributes are not mapped"):
        validate_config(_tag_config(key=["plant_code", "tag_name", "installed_on"]), _model())


def test_source_config_refuses_duplicate_yaml_keys(tmp_path: Path) -> None:
    config = tmp_path / "duplicate.yml"
    config.write_text(
        """source: demo_tags
source: overwritten
into: tag
from: ${catalog}.bronze.demo_tags
key: [plant_code]
fields: {plant_code: plant}
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate YAML key"):
        validate_source_config(config, ROOT / "model" / "model.yml")


def test_metadata_contains_required_datatypes_references_and_direct_parent_key() -> None:
    metadata = entity_metadata(_model(), "tag")
    assert metadata.identifiers == ("plant_code", "tag_name")
    assert metadata.attribute("critical_indicator").datatype == "BOOLEAN"
    assert metadata.attribute("tag_class_name").reference == "tag_class"
    process_parent = next(
        parent for parent in metadata.parents if parent.entity == "process_unit"
    )
    assert process_parent.key == ("plant_code", "process_unit_code")
    tag_parent = next(parent for parent in metadata.parents if parent.entity == "tag")
    assert tag_parent.child_key == ("plant_code", "parent_tag_name")
    assert tag_parent.key == ("plant_code", "tag_name")
    assert metadata.technical_columns[0].name == "spine_id"


def test_row_check_emits_the_two_acceptance_reasons_exactly() -> None:
    result = check_row(
        {
            "plant_code": " P-1 ",
            "tag_name": "T-8",
            "process_unit_code": " ",
            "tag_class_name": "WIDGET",
            "critical_indicator": "true",
        },
        entity_metadata(_model(), "tag"),
        key=["plant_code", "tag_name"],
        value_maps={"tag_class_name": {"SEP": "separator"}},
    )
    assert result.reasons == (
        "process_unit_code is required and missing",
        "WIDGET is not a valid tag class",
    )
    assert result.values["plant_code"] == "P-1"


def test_row_check_casts_and_never_turns_bad_values_into_silent_nulls() -> None:
    metadata = entity_metadata(_model(), "tag")
    row = {
        "plant_code": "P-1",
        "tag_name": "T-1",
        "process_unit_code": "U-1",
        "tag_class_name": "SEP",
        "critical_indicator": "not_boolean",
        "installed_on": "31/12/2025",
    }
    result = check_row(
        row,
        metadata,
        key=["plant_code", "tag_name"],
        value_maps={"tag_class_name": {"SEP": "separator"}},
    )
    assert "not_boolean is not a valid boolean for critical_indicator" in result.reasons
    assert "31/12/2025 is not a valid date for installed_on" in result.reasons
    assert result.values["critical_indicator"] is None
    assert result.values["installed_on"] is None

    assert cast_value(" false ", "BOOLEAN") is False
    assert cast_value("2025-12-31", "DATE") == date(2025, 12, 31)
    assert cast_value("42", "BIGINT") == 42


def test_internal_prepared_columns_are_valid_sql_identifiers() -> None:
    assert _prepared_column_name("plant_code") == "cfihos_prepared_plant_code"
    with pytest.raises(ValueError, match="invalid lowercase SQL identifier"):
        _prepared_column_name("Plant Code")


def test_row_check_uses_rdl_parent_and_enrich_rules() -> None:
    metadata = entity_metadata(_model(), "tag")
    row = {
        "plant_code": "P-1",
        "tag_name": "T-1",
        "process_unit_code": "U-9",
        "tag_class_name": "SEP",
        "critical_indicator": "true",
    }
    result = check_row(
        row,
        metadata,
        key=["plant_code", "tag_name"],
        mode="enrich",
        value_maps={"tag_class_name": {"SEP": "separator"}},
        rdl_values={"tag_class_name": {"centrifugal pump"}},
        parent_values={"process_unit_code": {("P-1", "U-1")}},
        existing=False,
    )
    assert result.reasons == (
        "separator is not a valid tag class",
        "no existing process unit for process_unit_code",
        "no existing tag to enrich",
    )


def test_enrich_rejects_a_blank_mapped_mandatory_attribute() -> None:
    result = check_row(
        {
            "plant_code": "P-1",
            "tag_name": "T-1",
            "process_unit_code": " ",
        },
        entity_metadata(_model(), "tag"),
        key=["plant_code", "tag_name"],
        mode="enrich",
    )
    assert result.reasons == ("process_unit_code is required and missing",)


def test_row_check_enforces_a_renamed_parent_key_without_guessing() -> None:
    result = check_row(
        {
            "plant_code": "P-1",
            "tag_name": "T-2",
            "parent_tag_name": "T-1",
            "process_unit_code": "U-1",
            "tag_class_name": "separator",
            "critical_indicator": "true",
        },
        entity_metadata(_model(), "tag"),
        key=["plant_code", "tag_name"],
        parent_values={"parent_tag_name": {("P-1", "T-0")}},
    )
    assert "no existing tag for parent_tag_name" in result.reasons


def test_core_rdl_manifest_is_derived_from_the_pinned_csvs() -> None:
    tables = expected_rdl_tables(ROOT / "spec" / "rdl")
    assert "tag_class" in tables
    assert "equipment_class" in tables


def test_rdl_column_selection_is_derived_from_attribute_and_reference() -> None:
    assert (
        rdl_value_column(
            "tag_class_name",
            "tag_class",
            ["cfihos_unique_code", "tag_class_name", "rdl_version"],
        )
        == "tag_class_name"
    )
    assert (
        rdl_value_column(
            "shelf_life_unit_of_measure_name",
            "unit_of_measure",
            ["cfihos_unique_code", "unit_of_measure_name", "rdl_version"],
        )
        == "unit_of_measure_name"
    )


def test_shipped_demo_configs_validate_against_generated_model() -> None:
    source_dir = ROOT / "src" / "conform" / "sources"
    configs = [
        validate_source_config(path)
        for path in sorted(source_dir.glob("demo_*.yml"))
    ]
    assert {config.into for config in configs} == {"plant", "process_unit", "tag"}


def test_quarantine_ddl_has_the_complete_plain_reason_record() -> None:
    ddl = (ROOT / "src" / "quarantine.sql").read_text(encoding="utf-8")
    assert "IOGP JIP36" in ddl
    assert "cfihos_quarantine" in ddl
    for column in (
        "source",
        "entity",
        "run_id",
        "source_key",
        "source_occurrence",
        "source_row_json",
        "reasons",
        "quarantined_at",
    ):
        assert f"`{column}`" in ddl
