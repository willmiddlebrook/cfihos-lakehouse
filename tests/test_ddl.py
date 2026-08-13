import re
from collections import Counter
from pathlib import Path

import yaml

from src.gen_ddl import generate

ROOT = Path(__file__).resolve().parents[1]


def test_generated_ddl_matches_checked_in_golden_files(tmp_path: Path) -> None:
    model = yaml.safe_load((ROOT / "model" / "model.yml").read_text(encoding="utf-8"))
    generated_report = tmp_path / "generation_report.yml"
    generated = generate(model, tmp_path, report_path=generated_report)
    checked_in = sorted((ROOT / "src" / "ddl").glob("*.sql"))
    assert [path.name for path in generated] == [path.name for path in checked_in]
    for actual, expected in zip(generated, checked_in, strict=True):
        assert actual.read_text(encoding="utf-8") == expected.read_text(encoding="utf-8")
    assert generated_report.read_text(encoding="utf-8") == (
        ROOT / "model" / "generation_report.yml"
    ).read_text(encoding="utf-8")


def test_every_spine_table_has_attribution_comments_and_informational_constraints() -> None:
    ddl_paths = sorted((ROOT / "src" / "ddl").glob("*.sql"))
    sql = "\n".join(path.read_text(encoding="utf-8") for path in ddl_paths)
    assert sql.count("CFIHOS materials are published by IOGP JIP36 under CC BY 4.0") == len(
        ddl_paths
    )
    assert "CFIHOS certified" in sql
    assert "PRIMARY KEY" in sql
    assert "NOT ENFORCED" in sql
    assert "constraints_enforced' = 'false" in sql


def test_generated_foreign_keys_reference_only_generated_spine_tables() -> None:
    sql = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "src/ddl").glob("*.sql"))
    created_tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([^\s(]+)", sql))
    referenced_tables = set(re.findall(r"REFERENCES\s+([^\s(]+)\s*\(", sql))
    assert referenced_tables
    assert referenced_tables <= created_tables


def test_foreign_keys_are_deferred_until_after_all_create_table_statements() -> None:
    ddl_paths = sorted((ROOT / "src" / "ddl").glob("*.sql"))
    assert ddl_paths[-1].name == "90_foreign_keys.sql"
    for path in ddl_paths[:-1]:
        assert "FOREIGN KEY" not in path.read_text(encoding="utf-8")
    foreign_key_sql = ddl_paths[-1].read_text(encoding="utf-8")
    assert "CREATE TABLE" not in foreign_key_sql
    assert foreign_key_sql.count("ALTER TABLE") == foreign_key_sql.count("FOREIGN KEY")


def test_generation_report_accounts_for_every_considered_foreign_key() -> None:
    model = yaml.safe_load((ROOT / "model" / "model.yml").read_text(encoding="utf-8"))
    report = yaml.safe_load(
        (ROOT / "model" / "generation_report.yml").read_text(encoding="utf-8")
    )
    emitted = report["fk_emitted"]
    skipped = report["fk_skipped"]
    summary = report["fk_summary"]
    expected_relationships = {
        (entity_name, attribute["name"], attribute["references"])
        for entity_name in model["generation"]["spine_entities"]
        for attribute in model["entities"][entity_name]["attributes"]
        if attribute.get("references")
    }
    reported_relationships = {
        (item["child"], item["attribute"], item["target"])
        for item in emitted + skipped
    }
    assert reported_relationships == expected_relationships
    assert summary["considered"] == len(expected_relationships)
    assert summary["emitted"] == len(emitted)
    assert summary["skipped"] == len(skipped)

    reasons = {
        "target_out_of_scope",
        "composite_target_key",
        "renamed_key",
        "target_has_no_single_identifier",
    }
    reason_counts = Counter(item["reason"] for item in skipped)
    assert set(reason_counts) <= reasons
    assert summary["skipped_by_reason"] == {
        reason: reason_counts.get(reason, 0) for reason in sorted(reasons)
    }
    assert all(set(item) == {"child", "attribute", "target"} for item in emitted)
    assert all(
        set(item) == {"child", "attribute", "target", "reason"} for item in skipped
    )
