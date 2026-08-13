from pathlib import Path

from src.acceptance import EXPECTED_COUNTS, EXPECTED_REASONS, FIXTURE_CSV

ROOT = Path(__file__).resolve().parents[1]


def test_embedded_acceptance_rows_are_identical_to_tutorial_csvs() -> None:
    for source, contents in FIXTURE_CSV.items():
        assert contents == (ROOT / "tutorial" / f"{source}.csv").read_text(encoding="utf-8")


def test_acceptance_contract_has_the_exact_outcomes() -> None:
    assert EXPECTED_COUNTS == {
        "plants": 1,
        "process_units": 2,
        "tags": 6,
        "quarantined": 2,
    }
    expected_reasons = {
        "process_unit_code is required and missing",
        "WIDGET is not a valid tag class",
    }
    assert expected_reasons == EXPECTED_REASONS
