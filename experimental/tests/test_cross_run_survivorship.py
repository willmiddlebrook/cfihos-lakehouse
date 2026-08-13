from src.trust.who_wins import resolve_claims


def _published(source: str, value: str | None, rank: int) -> dict[str, object]:
    return {"winning_source": source, "value": value, "wins_rank": rank}


def test_later_lower_priority_source_cannot_overwrite_current_winner() -> None:
    result = resolve_claims(
        [{"source_system": "source_low", "value": "INACTIVE", "wins_rank": 20}],
        current_winner=_published("source_high", "ACTIVE", 10),
    )

    assert result.winner is not None
    assert result.winner["source_system"] == "source_high"
    assert result.winner["value"] == "ACTIVE"
    assert result.conflicts == (
        {
            "source_system": "source_low",
            "value": "INACTIVE",
            "wins_rank": 20,
            "conflict_type": "losing_claim",
            "winning_source": "source_high",
        },
    )


def test_higher_priority_incoming_value_wins_and_displaced_value_stays_visible() -> None:
    result = resolve_claims(
        [{"source_system": "source_high", "value": "ACTIVE", "wins_rank": 10}],
        current_winner=_published("source_low", "INACTIVE", 20),
    )

    assert result.winner is not None
    assert result.winner["source_system"] == "source_high"
    assert len(result.conflicts) == 1
    displaced = result.conflicts[0]
    assert displaced["source_system"] == "source_low"
    assert displaced["value"] == "INACTIVE"
    assert displaced["conflict_type"] == "losing_claim"
    assert displaced["winning_source"] == "source_high"


def test_same_value_provenance_follows_rank_without_creating_a_value_conflict() -> None:
    promoted = resolve_claims(
        [{"source_system": "source_high", "value": "ACTIVE", "wins_rank": 10}],
        current_winner=_published("source_low", "ACTIVE", 20),
    )
    retained = resolve_claims(
        [{"source_system": "source_low", "value": "ACTIVE", "wins_rank": 20}],
        current_winner=_published("source_high", "ACTIVE", 10),
    )

    assert promoted.winner is not None
    assert promoted.winner["source_system"] == "source_high"
    assert promoted.conflicts == ()
    assert retained.winner is not None
    assert retained.winner["source_system"] == "source_high"
    assert retained.conflicts == ()


def test_new_observation_replaces_same_sources_current_observation() -> None:
    result = resolve_claims(
        [{"source_system": "source_a", "value": "INACTIVE", "wins_rank": 10}],
        current_winner=_published("source_a", "ACTIVE", 10),
    )

    assert result.winner is not None
    assert result.winner["value"] == "INACTIVE"
    assert result.conflicts == ()


def test_equal_cross_run_ranks_surface_a_tie_and_keep_both_claims_visible() -> None:
    result = resolve_claims(
        [{"source_system": "source_b", "value": "INACTIVE", "wins_rank": 10}],
        current_winner=_published("source_a", "ACTIVE", 10),
    )

    assert result.winner is None
    assert {claim["source_system"] for claim in result.conflicts} == {
        "source_a",
        "source_b",
    }
    assert {claim["conflict_type"] for claim in result.conflicts} == {"tied_rank"}


def test_cross_run_value_comparison_remains_null_safe() -> None:
    result = resolve_claims(
        [{"source_system": "source_low", "value": "ACTIVE", "wins_rank": 20}],
        current_winner=_published("source_high", None, 10),
    )

    assert result.winner is not None
    assert result.winner["value"] is None
    assert len(result.conflicts) == 1
    assert result.conflicts[0]["value"] == "ACTIVE"
    assert result.conflicts[0]["conflict_type"] == "losing_claim"
