from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_scope_cannot_drift_from_the_repository_contract() -> None:
    contract = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    scope = contract.split("## Scope\n\n", 1)[1].split("\n\nOUT OF SCOPE", 1)[0]
    out_of_scope = "OUT OF SCOPE" + contract.split("\n\nOUT OF SCOPE", 1)[1].split(
        "\n\n## Module disposition", 1
    )[0]

    assert scope in readme
    assert out_of_scope in readme


def test_readme_keeps_the_exact_acceptance_contract_and_attribution() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for required in (
        "| Plants landed | 1 |",
        "| Process units landed | 2 |",
        "| Tags landed | 6 |",
        "| Rows quarantined | 2 |",
        "process_unit_code is required and missing",
        "WIDGET is not a valid tag class",
        "experimental/README.md",
        "IOGP JIP36",
        "CC BY 4.0",
    ):
        assert required in readme


def test_core_notebooks_use_databricks_source_format() -> None:
    for name in ("00_get_started.py", "01_conform.py"):
        contents = (ROOT / "notebooks" / name).read_text(encoding="utf-8")
        assert contents.startswith("# Databricks notebook source\n")
        assert "# COMMAND ----------" in contents
        assert "# MAGIC %md" in contents


def test_experimental_scope_and_open_issues_are_recorded_verbatim() -> None:
    contents = (ROOT / "experimental" / "README.md").read_text(encoding="utf-8")
    assert (
        "Multi-system identity layer — matching, survivorship, stewardship — "
        "not part of the core product"
    ) in contents
    assert (
        "(1) engine.py re-runs re-insert already-mapped rows into id_map "
        "(new_maps includes direct); (2) who_wins compares values null-unsafely "
        "in the additions join and conflicts filter."
    ) in contents
