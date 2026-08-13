from pathlib import Path

import yaml

from src.gen_ddl import generate

ROOT = Path(__file__).resolve().parents[1]


def test_generated_ddl_matches_checked_in_golden_files(tmp_path: Path) -> None:
    model = yaml.safe_load((ROOT / "model" / "model.yml").read_text(encoding="utf-8"))
    generated = generate(model, tmp_path)
    checked_in = sorted((ROOT / "src" / "ddl").glob("*.sql"))
    assert [path.name for path in generated] == [path.name for path in checked_in]
    for actual, expected in zip(generated, checked_in, strict=True):
        assert actual.read_text(encoding="utf-8") == expected.read_text(encoding="utf-8")


def test_every_spine_table_has_attribution_comments_and_informational_constraints() -> None:
    sql = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((ROOT / "src" / "ddl").glob("*.sql"))
    )
    assert sql.count("CFIHOS materials are published by IOGP JIP36 under CC BY 4.0") == 5
    assert "CFIHOS certified" in sql
    assert "PRIMARY KEY" in sql
    assert "NOT ENFORCED" in sql
    assert "constraints_enforced' = 'false" in sql
