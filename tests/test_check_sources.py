from pathlib import Path

import pytest
import yaml

from tests.check_sources import (
    SourceContract,
    SourceContractError,
    check_sources,
    lint_contracts,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "sources"
MODEL = ROOT / "model" / "model.yml"


def test_sources_for_one_entity_must_use_the_same_key() -> None:
    with pytest.raises(SourceContractError, match="tag: key mismatch across sources"):
        check_sources(FIXTURES / "key_mismatch", MODEL)


def test_two_writers_need_upsert_mode_and_declared_territories() -> None:
    with pytest.raises(
        SourceContractError,
        match=r"tag\.tag_description: writer conflict between primary_tags and secondary_tags",
    ):
        check_sources(FIXTURES / "writer_conflict", MODEL)


def test_shipped_demo_contracts_print_order_and_ownership(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = check_sources(ROOT / "src" / "conform" / "sources", MODEL)

    output = capsys.readouterr().out
    assert "Run order: plants -> process_units -> tags" in output
    assert "Ownership matrix:" in output
    assert "plant | plant_code | demo_plants" in output
    assert "process_unit | process_unit_code | demo_process_units" in output
    assert "tag | tag_class_name | demo_tags" in output
    assert report.run_order == ("plant", "process_unit", "tag")


def test_enrich_keys_identify_rows_without_becoming_second_writers() -> None:
    model = yaml.safe_load(MODEL.read_text(encoding="utf-8"))
    contracts = (
        SourceContract(
            Path("base.yml"),
            "base_tags",
            "tag",
            ("plant_code", "tag_name"),
            "upsert",
            None,
            {
                "plant_code": "plant_code",
                "tag_name": "tag_name",
                "tag_description": "description",
            },
        ),
        SourceContract(
            Path("enrich.yml"),
            "tag_status_enrichment",
            "tag",
            ("plant_code", "tag_name"),
            "enrich",
            None,
            {
                "plant_code": "plant_code",
                "tag_name": "tag_name",
                "tag_status": "status",
            },
        ),
    )

    report = lint_contracts(contracts, model)

    assert ("tag", "tag_status", "tag_status_enrichment") in report.ownership
    assert ("tag", "plant_code", "tag_status_enrichment") not in report.ownership
