import pytest

from src.trust import steward as steward_module
from src.trust.materialize import (
    cast_attribute_value,
    missing_required,
    pending_replace_predicate,
    pivot_attributes,
    record_changed,
    required_attributes,
)
from src.trust.merge_service import merge_state, unmerge_state
from src.trust.spine_ids import mint_spine_id
from src.trust.steward import (
    confirm_as_new_state,
    confirm_to_existing_state,
    reject_state,
)
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


def test_null_and_non_null_claims_are_a_visible_conflict() -> None:
    result = resolve_claims(
        [
            {"source_system": "source_a", "value": None, "wins_rank": 1},
            {"source_system": "source_b", "value": "ACTIVE", "wins_rank": 2},
        ]
    )
    assert result.winner["source_system"] == "source_a"
    assert result.conflicts == (
        {
            "source_system": "source_b",
            "value": "ACTIVE",
            "wins_rank": 2,
            "conflict_type": "losing_claim",
            "winning_source": "source_a",
        },
    )


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


def test_registry_materialization_helpers_are_complete_and_null_safe() -> None:
    entity = {
        "attributes": [
            {"name": "code", "requirement": "identifier"},
            {"name": "name", "requirement": "mandatory"},
            {"name": "note", "requirement": "optional"},
        ]
    }
    assert required_attributes(entity) == ("code", "name")
    records = pivot_attributes(
        [
            {"spine_id": "one", "attribute": "code", "value": "A"},
            {"spine_id": "one", "attribute": "name", "value": "Alpha"},
        ]
    )
    assert missing_required(records["one"], required_attributes(entity)) == ()
    assert not record_changed(records["one"], dict(records["one"]), ("code", "name", "note"))
    assert record_changed(records["one"], {**records["one"], "note": "new"}, ("note",))
    assert missing_required({"code": "B", "name": None}, ("code", "name")) == ("name",)


def test_bad_boolean_and_date_values_fail_before_materialization() -> None:
    for value, datatype in (("sometimes", "BOOLEAN"), ("2026-02-30", "DATE")):
        try:
            cast_attribute_value(value, datatype)
        except ValueError as error:
            assert f"invalid {datatype} value" in str(error)
        else:
            raise AssertionError(f"bad {datatype} value did not fail")


def test_pending_records_are_a_current_work_pile() -> None:
    assert pending_replace_predicate("equipment") == "entity = 'equipment'"
    with pytest.raises(ValueError, match="invalid lowercase SQL identifier"):
        pending_replace_predicate("equipment' OR true")


def test_steward_queue_transitions_and_deterministic_origination() -> None:
    queue = {
        "queue_id": "queue-1",
        "source_system": "source_a",
        "entity": "equipment",
        "source_id": "asset-1",
        "status": "open",
        "candidate_spine_id": None,
        "resolved_by": None,
        "resolved_at": None,
        "reason": "No match",
    }
    expected = mint_spine_id("equipment", "source_a", "asset-1")
    resolved, new_mapping = confirm_as_new_state(queue, "steward")
    assert resolved["status"] == "confirmed"
    assert new_mapping["spine_id"] == expected
    assert new_mapping["match_tier"] == "steward"
    selected, existing_mapping = confirm_to_existing_state(queue, "spine-existing", "steward")
    assert selected["candidate_spine_id"] == "spine-existing"
    assert existing_mapping["spine_id"] == "spine-existing"
    rejected = reject_state(queue, "steward", "not the same asset")
    assert rejected["status"] == "rejected"
    assert rejected["resolved_by"] == "steward"


def test_steward_cannot_resolve_a_closed_queue_item() -> None:
    closed = {
        "queue_id": "queue-1",
        "source_system": "source_a",
        "entity": "equipment",
        "source_id": "asset-1",
        "status": "rejected",
    }
    for transition in (
        lambda: confirm_to_existing_state(closed, "spine-existing", "steward"),
        lambda: confirm_as_new_state(closed, "steward"),
        lambda: reject_state(closed, "steward", "still rejected"),
    ):
        try:
            transition()
        except ValueError as error:
            assert "not open" in str(error)
        else:
            raise AssertionError("closed queue transition did not fail")


def test_confirm_to_existing_rejects_missing_target_spine_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = {
        "queue_id": "queue-1",
        "source_system": "source_a",
        "entity": "equipment",
        "source_id": "asset-1",
        "status": "open",
        "candidate_spine_id": None,
        "resolved_by": None,
        "resolved_at": None,
        "reason": "No match",
    }
    writes: list[str] = []

    class MissingSpineFrame:
        def filter(self, condition: str) -> "MissingSpineFrame":
            assert condition == "is_current = true"
            return self

        def join(
            self, other: object, columns: str, how: str
        ) -> "MissingSpineFrame":
            assert columns == "spine_id"
            assert how == "inner"
            return self

        def limit(self, records: int) -> "MissingSpineFrame":
            assert records == 1
            return self

        def count(self) -> int:
            return 0

    class MissingSpineSpark:
        def createDataFrame(self, rows: list[tuple[str]], schema: str) -> object:
            assert rows == [("missing-spine",)]
            assert schema == "spine_id string"
            return object()

        def table(self, name: str) -> MissingSpineFrame:
            assert name == "cfihos_tutorial.cfihos_physical_asset.equipment"
            return MissingSpineFrame()

    monkeypatch.setattr(steward_module, "_queue_row", lambda *_: queue)
    monkeypatch.setattr(
        steward_module, "_append_mapping", lambda *_: writes.append("id_map")
    )
    monkeypatch.setattr(
        steward_module, "_apply_queue_update", lambda *_: writes.append("queue")
    )

    with pytest.raises(
        ValueError,
        match="missing-spine.*does not exist for target entity.*equipment",
    ):
        steward_module.confirm_to_existing(
            MissingSpineSpark(),
            "cfihos_tutorial",
            "queue-1",
            "missing-spine",
            "steward",
        )

    assert writes == []
