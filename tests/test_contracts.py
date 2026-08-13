from pathlib import Path

import yaml

from src.deploy_foundation import split_sql_statements
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
