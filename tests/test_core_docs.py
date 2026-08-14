from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _notebook_commands(name: str) -> list[str]:
    contents = (ROOT / "notebooks" / name).read_text(encoding="utf-8")
    body = contents.removeprefix("# Databricks notebook source\n")
    return body.split("# COMMAND ----------")


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

        for command in _notebook_commands(name):
            lines = [line for line in command.splitlines() if line.strip()]
            if any(line.startswith("# MAGIC") for line in lines):
                assert all(line.startswith("# MAGIC") for line in lines), (
                    f"{name} mixes Markdown magic with Python in one command"
                )


def test_core_notebooks_work_from_a_fresh_git_folder() -> None:
    started = (ROOT / "notebooks" / "00_get_started.py").read_text(encoding="utf-8")
    conform = (ROOT / "notebooks" / "01_conform.py").read_text(encoding="utf-8")

    assert started.count('dbutils.widgets.text("catalog", "cfihos_demo")') == 1
    assert conform.count('dbutils.widgets.text("catalog", "cfihos_demo")') == 1
    assert "Use the exact same catalog as notebook 00" in conform
    assert "USE CATALOG" in started
    assert "CREATE SCHEMA" in started

    for name in ("00_get_started.py", "01_conform.py"):
        for command in _notebook_commands(name):
            if 'dbutils.widgets.text("catalog"' in command:
                assert 'dbutils.widgets.get("catalog")' not in command

    install = "# MAGIC %pip install PyYAML==6.0.2"
    assert install in conform
    assert conform.index(install) < conform.index("from src.conform import")
    assert "yaml_file must not be empty" in conform
    assert "yaml_file must end in .yml or .yaml" in conform


def test_conform_notebook_shows_persisted_results_and_retained_rejections() -> None:
    contents = (ROOT / "notebooks" / "01_conform.py").read_text(encoding="utf-8")
    for required in (
        "valid_rows_this_run",
        "invalid_rows_this_run",
        "target_table",
        "persisted_rows_after_run",
        "Quarantine history",
        "retained rejection history",
        '"run_id"',
        ".limit(100)",
    ):
        assert required in contents


def test_readme_links_the_verified_databricks_walkthrough() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    walkthrough = (ROOT / "docs" / "databricks-walkthrough.md").read_text(
        encoding="utf-8"
    )

    assert "docs/databricks-walkthrough.md" in readme
    for required in (
        "Run its first Python setup cell once",
        "exact same value used in notebook 00",
        "demo_plants.yml",
        "demo_process_units.yml",
        "demo_tags.yml",
        "1 / 2 / 6 / 2",
        "process_unit_code is required and missing",
        "WIDGET is not a valid tag class",
        "omit the `.py` suffix",
    ):
        assert required in walkthrough


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
