from src.trust.merge_service import merge_state, unmerge_state
from src.trust.who_wins import resolve_claims


def test_losing_claim_is_visible() -> None:
    result = resolve_claims(
        [
            {"source_system": "source_a", "value": "ACTIVE", "wins_rank": 1},
            {"source_system": "source_b", "value": "INACTIVE", "wins_rank": 2},
        ]
    )
    assert result.winner["source_system"] == "source_a"
    assert result.conflicts[0]["conflict_type"] == "losing_claim"


def test_tied_claim_is_not_resolved_arbitrarily() -> None:
    result = resolve_claims(
        [
            {"source_system": "source_a", "value": "ACTIVE", "wins_rank": 1},
            {"source_system": "source_b", "value": "INACTIVE", "wins_rank": 1},
        ]
    )
    assert result.winner is None
    assert {item["conflict_type"] for item in result.conflicts} == {"tied_rank"}


def test_merge_then_unmerge_restores_the_prior_crosswalk() -> None:
    initial = [
        {"source_system": "source_a", "entity": "equipment", "source_id": "1", "spine_id": "A"},
        {"source_system": "source_b", "entity": "equipment", "source_id": "2", "spine_id": "B"},
    ]
    merged, merge_event = merge_state(initial, "A", "B", "steward", "same serial")
    assert {row["spine_id"] for row in merged} == {"A"}
    restored, unmerge_event = unmerge_state(merged, merge_event, "steward", "incorrect merge")
    assert restored == initial
    assert unmerge_event["reverses_event_id"] == merge_event["event_id"]
