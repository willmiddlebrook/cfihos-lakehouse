"""Enforce the constraints that Unity Catalog declares informationally."""

from __future__ import annotations

import argparse
import json
import re
import uuid
from pathlib import Path
from typing import Any

import yaml


def validate(spark: Any, catalog: str, model: dict[str, Any]) -> list[dict[str, Any]]:
    from pyspark.sql import functions as F

    run_id = str(uuid.uuid4())
    results: list[dict[str, Any]] = []

    def record(check: str, object_name: str, failed_rows: int, details: str = "") -> None:
        results.append(
            {
                "validation_run_id": run_id,
                "check_name": check,
                "object_name": object_name,
                "failed_rows": int(failed_rows),
                "status": "PASS" if failed_rows == 0 else "FAIL",
                "details": details,
            }
        )

    for entity_name in model["generation"]["spine_entities"]:
        entity = model["entities"][entity_name]
        table = f"{catalog}.cfihos_{entity['subject_area']}.{entity_name}"
        if not spark.catalog.tableExists(table):
            record("table_exists", table, 1, "generated spine table is missing")
            continue
        frame = spark.table(table)
        identifiers = [
            item["name"] for item in entity["attributes"] if item["requirement"] == "identifier"
        ]
        required = [
            item["name"]
            for item in entity["attributes"]
            if item["requirement"] in {"identifier", "mandatory"}
        ]
        if required:
            null_condition = reduce_or([F.col(column).isNull() for column in required])
            record("required_values", table, frame.filter(null_condition).count())
        if identifiers:
            duplicate_rows = (
                frame.groupBy(*identifiers).count().filter(F.col("count") > 1).count()
            )
            record("primary_key_unique", table, duplicate_rows)

    id_map = spark.table(f"{catalog}.cfihos_trust.id_map")
    id_map_duplicates = (
        id_map.groupBy("source_system", "entity", "source_id")
        .count()
        .filter(F.col("count") > 1)
        .count()
    )
    record("id_map_unique", f"{catalog}.cfihos_trust.id_map", id_map_duplicates)
    record(
        "id_map_tier",
        f"{catalog}.cfihos_trust.id_map",
        id_map.filter(~F.col("match_tier").isin("exact", "normalized", "steward")).count(),
    )
    queue = spark.table(f"{catalog}.cfihos_trust.review_queue")
    record(
        "review_status",
        f"{catalog}.cfihos_trust.review_queue",
        queue.filter(~F.col("status").isin("open", "confirmed", "rejected")).count(),
    )
    audit = spark.table(f"{catalog}.cfihos_ref.load_audit")
    record(
        "rdl_reconciliation",
        f"{catalog}.cfihos_ref.load_audit",
        audit.filter(
            F.col("source_rows") != F.col("loaded_rows") + F.col("exception_rows")
        ).count(),
    )
    exceptions = spark.table(f"{catalog}.cfihos_ref.load_exceptions")
    record(
        "rdl_unexplained_exceptions",
        f"{catalog}.cfihos_ref.load_exceptions",
        exceptions.filter(~F.col("explained")).count(),
    )
    output = spark.createDataFrame(results).withColumn("checked_at", F.current_timestamp())
    output.write.mode("append").saveAsTable(f"{catalog}.cfihos_trust.validation_results")
    return results


def reduce_or(conditions: list[Any]) -> Any:
    if not conditions:
        raise ValueError("at least one condition is required")
    result = conditions[0]
    for condition in conditions[1:]:
        result = result | condition
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument(
        "--model", type=Path, default=Path(__file__).resolve().parents[1] / "model" / "model.yml"
    )
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.catalog):
        raise ValueError("catalog must be a lowercase SQL identifier")
    model = yaml.safe_load(args.model.read_text(encoding="utf-8"))
    from pyspark.sql import SparkSession

    results = validate(SparkSession.builder.getOrCreate(), args.catalog, model)
    failed = [item for item in results if item["status"] == "FAIL"]
    print(json.dumps({"checks": len(results), "failed": failed}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
