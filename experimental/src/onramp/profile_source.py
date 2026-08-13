"""Profile a governed source table for an agent-assisted mapping proposal."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_SCRIPT_PATH = Path(globals().get("__file__", sys.argv[0])).resolve()


def _validate_inputs(catalog: str, source: str, table_name: str) -> None:
    try:
        from src.identifiers import validate_identifier
    except ModuleNotFoundError:  # Serverless Python-file tasks put src/ on sys.path.
        sys.path.insert(0, str(_SCRIPT_PATH.parents[1]))
        from identifiers import validate_identifier

    validate_identifier(catalog)
    validate_identifier(source)
    table_parts = table_name.split(".")
    if len(table_parts) != 3:
        raise ValueError("table must be a Unity Catalog three-part name")
    for part in table_parts:
        validate_identifier(part)
    if table_parts[0] != catalog:
        raise ValueError("table catalog must equal --catalog")


def _quoted_column(name: str) -> str:
    return f"`{name.replace('`', '``')}`"


def build_profile(
    spark: Any,
    source: str,
    table_name: str,
    *,
    profiled_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic, serializable profile without writing it."""

    from pyspark.sql import functions as F

    frame = spark.table(table_name)
    row_count = frame.count()
    columns: list[dict[str, Any]] = []
    for field in frame.schema.fields:
        value = F.col(_quoted_column(field.name)).cast("string").alias("value")
        values = frame.select(value)
        null_count = frame.filter(F.col(_quoted_column(field.name)).isNull()).count()
        distinct_values = values.filter(F.col("value").isNotNull()).distinct().orderBy("value")
        distinct_count = distinct_values.count()
        sample_values = [row["value"] for row in distinct_values.limit(10).collect()]
        column_profile: dict[str, Any] = {
            "name": field.name,
            "type": field.dataType.simpleString(),
            "null_fraction": round(null_count / row_count, 6) if row_count else 0.0,
            "distinct_count": distinct_count,
            "sample_values": sample_values,
        }
        if distinct_count <= 25:
            column_profile["distinct_values"] = [
                row["value"] for row in distinct_values.collect()
            ]
        columns.append(column_profile)
    observed_at = profiled_at or datetime.now(timezone.utc)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("profiled_at must include a timezone")
    observed_at = observed_at.astimezone(timezone.utc)
    return {
        "profile_version": 1,
        "source": source,
        "profiled_at": observed_at.isoformat().replace("+00:00", "Z"),
        "tables": [
            {
                "table_name": table_name,
                "row_count": row_count,
                "columns": columns,
            }
        ],
    }


def profile_source(spark: Any, catalog: str, source: str, table_name: str) -> str:
    """Profile a source, persist the evidence, and return the exact YAML text."""

    from pyspark.sql import functions as F

    _validate_inputs(catalog, source, table_name)
    profile = build_profile(spark, source, table_name)
    profile_yaml = yaml.safe_dump(profile, sort_keys=False, allow_unicode=True)
    spark.createDataFrame(
        [(source, table_name, profile_yaml)],
        "source string, table_name string, profile_yaml string",
    ).withColumn("profiled_at", F.current_timestamp()).write.mode("append").saveAsTable(
        f"{catalog}.cfihos_onramp.source_profiles"
    )
    return profile_yaml


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--table", required=True)
    args = parser.parse_args(argv)
    from pyspark.sql import SparkSession

    profile_yaml = profile_source(
        SparkSession.builder.getOrCreate(), args.catalog, args.source, args.table
    )
    print(profile_yaml, end="")
    return 0


if __name__ == "__main__":
    main()
