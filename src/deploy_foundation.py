"""Apply all generated foundation, trust, health, and front-door SQL assets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_SCRIPT_PATH = Path(globals().get("__file__", sys.argv[0])).resolve()


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL on semicolons outside strings and line comments."""
    statements: list[str] = []
    current: list[str] = []
    index = 0
    in_string = False
    in_comment = False
    while index < len(sql):
        char = sql[index]
        following = sql[index + 1] if index + 1 < len(sql) else ""
        if in_comment:
            current.append(char)
            if char == "\n":
                in_comment = False
            index += 1
            continue
        if not in_string and char == "-" and following == "-":
            current.extend((char, following))
            in_comment = True
            index += 2
            continue
        if char == "'":
            current.append(char)
            if in_string and following == "'":
                current.append(following)
                index += 2
                continue
            in_string = not in_string
            index += 1
            continue
        if char == ";" and not in_string:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        index += 1
    if in_string:
        raise ValueError("unterminated SQL string literal")
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def ensure_catalog(spark: Any, catalog: str) -> None:
    existing = {row[0] for row in spark.sql("SHOW CATALOGS").collect()}
    if catalog in existing:
        return
    spark.sql(
        f"CREATE CATALOG IF NOT EXISTS `{catalog}` "
        "COMMENT 'CFIHOS v2.0-aligned consolidation hub'"
    )


def deploy(spark: Any, root: Path, catalog: str) -> None:
    ensure_catalog(spark, catalog)
    paths = [
        *sorted((root / "src" / "ddl").glob("*.sql")),
        root / "src" / "trust" / "ddl_idmap.sql",
        root / "src" / "trust" / "health_views.sql",
        root / "src" / "front_door" / "metric_views.sql",
    ]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing generated/deployment SQL: {missing}")
    for path in paths:
        rendered = path.read_text(encoding="utf-8").replace("${catalog}", catalog)
        for statement in split_sql_statements(rendered):
            spark.sql(statement)
    print(f"applied {len(paths)} SQL files to {catalog}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    args = parser.parse_args(argv)
    from pyspark.sql import SparkSession

    deploy(SparkSession.builder.getOrCreate(), _SCRIPT_PATH.parents[1], args.catalog)
    return 0


if __name__ == "__main__":
    main()
