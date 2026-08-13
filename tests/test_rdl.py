from pathlib import Path

from src.load_rdl import parse_csv

ROOT = Path(__file__).resolve().parents[1]


def test_every_core_rdl_file_reconciles_without_silent_skips() -> None:
    batches = [parse_csv(path) for path in sorted((ROOT / "spec" / "rdl").glob("*.csv"))]
    assert len(batches) == 21
    assert sum(len(batch.rows) for batch in batches) == 42_472
    exceptions = [exception for batch in batches for exception in batch.exceptions]
    assert len(exceptions) == 1_281
    assert all(exception.reason.startswith("duplicate natural key") for exception in exceptions)
    assert sum(len(batch.rows) + len(batch.exceptions) for batch in batches) == 43_753
    assert all("_natural_key" in batch.columns for batch in batches)
    assert {batch.encoding for batch in batches} == {"utf-8-sig", "cp1252"}


def test_rdl_natural_keys_are_deterministic() -> None:
    path = ROOT / "spec" / "rdl" / "CFIHOS CORE discipline v2.0.csv"
    first = parse_csv(path)
    second = parse_csv(path)
    assert [row["_natural_key"] for row in first.rows] == [
        row["_natural_key"] for row in second.rows
    ]
