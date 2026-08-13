from pathlib import Path

import yaml

from src.onramp.engine import process_rows
from src.trust.merge_service import merge_state, unmerge_state
from src.trust.who_wins import resolve_claims

ROOT = Path(__file__).resolve().parents[1]


def test_planted_defects_all_reach_their_named_surfaces() -> None:
    config = yaml.safe_load(
        (ROOT / "src" / "onramp" / "sources" / "example_cmms.yml").read_text(encoding="utf-8")
    )
    rows = [
        {
            "location_id": "unknown-code",
            "plant_code": "P",
            "functional_location_code": "P-100",
            "description": "fixture",
            "status": "UNKNOWN",
        },
        {
            "location_id": "variant-duplicate",
            "plant_code": "P",
            "functional_location_code": "ASSET-P-100",
            "description": "fixture",
            "status": "OPERATING",
        },
    ]
    candidates = [
        {"tag_name": "P-100", "spine_id": "one"},
        {"tag_name": "LOC-P-100", "spine_id": "two"},
    ]
    result = process_rows(config, "tag", rows, candidates)
    conflict = resolve_claims(
        [
            {"source_system": "source_a", "value": "ACTIVE", "wins_rank": 1},
            {"source_system": "source_b", "value": "INACTIVE", "wins_rank": 1},
        ]
    )
    assert len(result["unmapped"]) == 1
    assert len(result["review"]) == 1
    assert conflict.winner is None
    assert result["matched"] == []


def test_acceptance_unmerge_round_trip() -> None:
    prior = [
        {"source_system": "source_a", "entity": "tag", "source_id": "x", "spine_id": "A"},
        {"source_system": "source_b", "entity": "tag", "source_id": "y", "spine_id": "B"},
    ]
    merged, event = merge_state(prior, "A", "B", "steward", "fixture")
    restored, reverse = unmerge_state(merged, event, "steward", "fixture reversal")
    assert restored == prior
    assert [event["event_type"], reverse["event_type"]] == ["merge", "unmerge"]
