import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import yaml

from src.deploy_foundation import ensure_catalog, split_sql_statements
from src.onramp.engine import validate_config

ROOT = Path(__file__).resolve().parents[1]


def test_engine_config_producer_consumer_contracts() -> None:
    model = yaml.safe_load((ROOT / "model" / "model.yml").read_text(encoding="utf-8"))
    configs = (ROOT / "src" / "onramp" / "sources").glob("*.yml")
    assert all(
        not validate_config(yaml.safe_load(path.read_text(encoding="utf-8")), model)
        for path in configs
    )


def test_sql_splitter_preserves_semicolons_and_escaped_quotes_in_comments() -> None:
    sql = "CREATE TABLE t (c STRING COMMENT 'owner''s; value'); -- one; two\nSELECT 1;"
    statements = split_sql_statements(sql)
    assert len(statements) == 2
    assert "owner''s; value" in statements[0]
    assert statements[1].endswith("SELECT 1")


def test_foundation_does_not_recreate_an_existing_governed_catalog() -> None:
    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [("governed_catalog",)]
    ensure_catalog(spark, "governed_catalog")
    spark.sql.assert_called_once_with("SHOW CATALOGS")


def test_serverless_entrypoints_resolve_paths_without_dunder_file(monkeypatch) -> None:
    entrypoints = [
        ROOT / "src" / "deploy_foundation.py",
        ROOT / "src" / "load_rdl.py",
        ROOT / "src" / "acceptance.py",
        ROOT / "src" / "validate.py",
        ROOT / "src" / "onramp" / "engine.py",
    ]
    for index, path in enumerate(entrypoints):
        assert "raise SystemExit" not in path.read_text(encoding="utf-8")
        monkeypatch.setattr(sys, "argv", [str(path)])
        module = ModuleType(f"serverless_path_probe_{index}")
        monkeypatch.setitem(sys.modules, module.__name__, module)
        exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
        assert path.resolve() == module._SCRIPT_PATH


def test_no_preview_dependency_tags_are_present() -> None:
    checked = [
        ROOT / "databricks.yml",
        *ROOT.joinpath("resources").glob("*.yml"),
        *ROOT.joinpath("src").rglob("*.py"),
        *ROOT.joinpath("src").rglob("*.sql"),
    ]
    contents = "\n".join(path.read_text(encoding="utf-8") for path in checked)
    assert "[Beta]" not in contents
    assert "[Private Preview]" not in contents
    assert "[Experimental]" not in contents
