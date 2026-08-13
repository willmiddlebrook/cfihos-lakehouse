import hashlib
from pathlib import Path

import yaml

from src.onramp.config_contract import validate_value_map_targets
from src.onramp.validate_proposal import validate_proposal


def _write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def _fixture(
    root: Path,
    *,
    reference: str = "status_reference",
    target: str = "ACTIVE",
    acknowledge: bool = False,
    extra_profile_column: bool = False,
    evidence_kinds: tuple[str, ...] = ("definition_match", "sample_fit"),
    stale_profile_pin: bool = False,
) -> tuple[Path, Path, dict, dict]:
    model = {
        "metadata": {"source_sha256": "model-source-hash", "cfihos_version": "2.0"},
        "entities": {
            "asset": {
                "attributes": [
                    {
                        "name": "status",
                        "requirement": "mandatory",
                        "references": reference,
                    }
                ]
            },
            "status_reference": {
                "attributes": [
                    {
                        "name": "status_name",
                        "requirement": "identifier",
                        "references": "",
                    }
                ]
            },
        },
    }
    candidate = {
        "source": "fixture_source",
        "arrives_as": "table",
        "feeds": {
            "asset": {
                "from": "fixture_catalog.bronze.fixture_asset",
                "source_id": "record_id",
                "match_on": ["status"],
                "fields": {"status": "raw_status"},
            }
        },
        "claims": {"asset.status": {"field": "raw_status", "wins_rank": 10}},
        "value_maps": {"asset.status": {"SOURCE_ACTIVE": target}},
        "unmatched": "review_queue",
    }
    columns = [
        {
            "name": "record_id",
            "type": "string",
            "null_fraction": 0.0,
            "distinct_count": 1,
            "sample_values": ["one"],
            "distinct_values": ["one"],
        },
        {
            "name": "raw_status",
            "type": "string",
            "null_fraction": 0.0,
            "distinct_count": 1,
            "sample_values": ["SOURCE_ACTIVE"],
            "distinct_values": ["SOURCE_ACTIVE"],
        },
    ]
    if extra_profile_column:
        columns.append(
            {
                "name": "unaccounted_column",
                "type": "string",
                "null_fraction": 0.0,
                "distinct_count": 1,
                "sample_values": ["unmapped"],
                "distinct_values": ["unmapped"],
            }
        )
    profile = {
        "profile_version": 1,
        "source": "fixture_source",
        "profiled_at": "2026-08-13T17:00:00Z",
        "tables": [
            {
                "table_name": "fixture_catalog.bronze.fixture_asset",
                "row_count": 1,
                "columns": columns,
            }
        ],
    }

    model_path = root / "model" / "model.yml"
    candidate_path = root / "src" / "onramp" / "sources" / "fixture_source.yml"
    profile_path = root / "src" / "onramp" / "profiles" / "fixture_source.yml"
    proposal_path = (
        root / "src" / "onramp" / "proposals" / "fixture_source.proposal.yml"
    )
    _write_yaml(model_path, model)
    _write_yaml(candidate_path, candidate)
    _write_yaml(profile_path, profile)
    if reference == "status_reference":
        rdl_path = root / "spec" / "rdl" / "CFIHOS CORE status reference v2.0.csv"
        rdl_path.parent.mkdir(parents=True, exist_ok=True)
        rdl_path.write_text("status name\nACTIVE\nINACTIVE\n", encoding="utf-8")

    profile_hash = hashlib.sha256(profile_path.read_bytes()).hexdigest()
    evidence = [
        {"kind": kind, "note": f"Fixture evidence for {kind}."} for kind in evidence_kinds
    ]
    proposal = {
        "proposal_version": 1,
        "source": "fixture_source",
        "generated_by": "fixture/agent",
        "generated_at": "2026-08-13T17:00:00Z",
        "pins": {
            "model_sha256": "model-source-hash",
            "rdl_version": "2.0",
            "profile_file": "src/onramp/profiles/fixture_source.yml",
            "profile_sha256": "0" * 64 if stale_profile_pin else profile_hash,
        },
        "mappings": [
            {
                "entity": "asset",
                "attribute": "status",
                "source_column": "raw_status",
                "tier": "certain",
                "evidence": evidence,
            }
        ],
        "value_map_summaries": [
            {"key": "asset.status", "distinct_seen": 1, "mapped": 1, "abstained": 0}
        ],
        "match_on_rationale": "Status is the interview-approved fixture match key.",
        "wins_rank_rationale": "Rank 10 is tied to the fixture source interview.",
        "abstained": {"columns": [], "codes": []},
        "unverifiable_targets": (
            [{"key": "asset.status", "basis": "No reference is defined in the model."}]
            if acknowledge
            else []
        ),
    }
    _write_yaml(proposal_path, proposal)
    return proposal_path, candidate_path, candidate, model


def test_valid_proposal_pair_passes(tmp_path: Path) -> None:
    proposal, candidate, _, _ = _fixture(tmp_path)
    assert validate_proposal(proposal, candidate, tmp_path) == []


def test_profile_column_must_be_accounted_for(tmp_path: Path) -> None:
    proposal, candidate, _, _ = _fixture(tmp_path, extra_profile_column=True)
    errors = validate_proposal(proposal, candidate, tmp_path)
    assert any("profile column unaccounted_column" in error for error in errors)


def test_stale_profile_pin_fails(tmp_path: Path) -> None:
    proposal, candidate, _, _ = _fixture(tmp_path, stale_profile_pin=True)
    assert "stale profile_sha256 pin" in validate_proposal(proposal, candidate, tmp_path)


def test_certain_mapping_needs_two_evidence_kinds(tmp_path: Path) -> None:
    proposal, candidate, _, _ = _fixture(tmp_path, evidence_kinds=("definition_match",))
    errors = validate_proposal(proposal, candidate, tmp_path)
    assert any("certain tier requires at least 2 evidence kinds" in error for error in errors)


def test_all_targets_present_in_core_rdl_pass(tmp_path: Path) -> None:
    _, _, candidate, model = _fixture(tmp_path)
    result = validate_value_map_targets(candidate, model, tmp_path / "spec" / "rdl")
    assert result.errors == ()
    assert result.warnings == ()


def test_bogus_target_names_reference_table(tmp_path: Path) -> None:
    _, _, candidate, model = _fixture(tmp_path, target="NOT_IN_RDL")
    result = validate_value_map_targets(candidate, model, tmp_path / "spec" / "rdl")
    assert len(result.errors) == 1
    assert "NOT_IN_RDL" in result.errors[0]
    assert "cfihos_ref.status_reference" in result.errors[0]


def test_no_reference_returns_structured_warning(tmp_path: Path) -> None:
    _, _, candidate, model = _fixture(tmp_path, reference="", acknowledge=True)
    result = validate_value_map_targets(candidate, model, tmp_path / "spec" / "rdl")
    assert result.errors == ()
    assert result.warnings[0].as_dict() == {
        "key": "asset.status",
        "status": "unverifiable",
        "reason": "attribute_has_no_reference",
        "reference_entity": None,
        "reference_table": None,
    }


def test_acknowledged_unverifiable_target_passes(tmp_path: Path) -> None:
    proposal, candidate, _, _ = _fixture(tmp_path, reference="", acknowledge=True)
    assert validate_proposal(proposal, candidate, tmp_path) == []


def test_unacknowledged_unverifiable_target_fails(tmp_path: Path) -> None:
    proposal, candidate, _, _ = _fixture(tmp_path, reference="", acknowledge=False)
    errors = validate_proposal(proposal, candidate, tmp_path)
    assert any(
        "unverifiable value_map asset.status needs an acknowledgement" in error
        for error in errors
    )
