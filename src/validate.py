"""Enforce the constraints that Unity Catalog declares informationally."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

try:
    from src.identifiers import validate_identifier
except ModuleNotFoundError:  # Serverless Python-file tasks put src/ on sys.path.
    from identifiers import validate_identifier

_SCRIPT_PATH = Path(globals().get("__file__", sys.argv[0])).resolve()


def validate(
    spark: Any,
    catalog: str,
    model: dict[str, Any],
    generation_report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    validate_identifier(catalog)
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
        current = frame.filter(F.col("is_current"))
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
            record("required_values", table, current.filter(null_condition).count())
        if identifiers:
            duplicate_rows = (
                current.groupBy(*identifiers).count().filter(F.col("count") > 1).count()
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
        id_map.filter(
            ~F.col("match_tier").isin("exact", "normalized", "steward", "founding")
        ).count(),
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
    if generation_report is not None:
        for foreign_key in generation_report["foreign_keys"]["emitted"]:
            source_entity = model["entities"][foreign_key["source_entity"]]
            target_entity = model["entities"][foreign_key["target_entity"]]
            source_table = (
                f"{catalog}.cfihos_{source_entity['subject_area']}."
                f"{foreign_key['source_entity']}"
            )
            target_table = (
                f"{catalog}.cfihos_{target_entity['subject_area']}."
                f"{foreign_key['target_entity']}"
            )
            if not (
                spark.catalog.tableExists(source_table)
                and spark.catalog.tableExists(target_table)
            ):
                continue
            source_rows = spark.table(source_table).filter(F.col("is_current")).alias("child")
            target_rows = spark.table(target_table).filter(F.col("is_current")).alias("parent")
            source_attribute = foreign_key["source_attribute"]
            target_attribute = foreign_key["target_attribute"]
            orphans = (
                source_rows.filter(F.col(f"child.{source_attribute}").isNotNull())
                .join(
                    target_rows,
                    F.col(f"child.{source_attribute}")
                    == F.col(f"parent.{target_attribute}"),
                    "left_anti",
                )
                .count()
            )
            record(
                f"fk_orphans_{foreign_key['source_entity']}_{source_attribute}",
                source_table,
                orphans,
                f"target={target_table}.{target_attribute}",
            )
    missing_comments = spark.sql(
        f"""SELECT count(*) AS records
        FROM {catalog}.information_schema.tables
        WHERE table_schema LIKE 'cfihos_%'
          AND table_type <> 'VIEW'
          AND (comment IS NULL OR trim(comment) = '')"""
    ).first().records
    record(
        "table_comments",
        f"{catalog}.information_schema.tables",
        missing_comments,
        "Every CFIHOS managed table must explain its purpose.",
    )
    pending_count = spark.table(f"{catalog}.cfihos_trust.pending_records").count()
    record(
        "pending_records",
        f"{catalog}.cfihos_trust.pending_records",
        0,
        f"pending_count={pending_count}; informational only",
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
        "--model", type=Path, default=_SCRIPT_PATH.parents[1] / "model" / "model.yml"
    )
    parser.add_argument(
        "--generation-report",
        type=Path,
        default=_SCRIPT_PATH.parents[1] / "model" / "generation_report.yml",
    )
    args = parser.parse_args(argv)
    validate_identifier(args.catalog)
    model = yaml.safe_load(args.model.read_text(encoding="utf-8"))
    generation_report = yaml.safe_load(args.generation_report.read_text(encoding="utf-8"))
    from pyspark.sql import SparkSession

    results = validate(
        SparkSession.builder.getOrCreate(), args.catalog, model, generation_report
    )
    failed = [item for item in results if item["status"] == "FAIL"]
    print(json.dumps({"checks": len(results), "failed": failed}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    if main():
        raise RuntimeError("CFIHOS constraint validation failed")
