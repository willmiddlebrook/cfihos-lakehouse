"""Run the Core v1 CSV acceptance contract against a Unity Catalog catalog."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from src.conform import conform
    from src.deploy_foundation import deploy
    from src.identifiers import validate_identifier
    from src.load_rdl import load_rdl
except ModuleNotFoundError:  # Serverless Python-file tasks put src/ on sys.path.
    from conform import conform
    from deploy_foundation import deploy
    from identifiers import validate_identifier
    from load_rdl import load_rdl

_SCRIPT_PATH = Path(globals().get("__file__", sys.argv[0])).resolve()

FIXTURE_CSV = {
    "demo_plants": """plant_code,plant_name
P-004,Compressor Station 4
""",
    "demo_process_units": """plant_code,process_unit_code,process_unit_name
P-004,U-100,Inlet Separation
P-004,U-200,Compression
""",
    "demo_tags": """plant_code,tag_name,tag_description,process_unit_code,tag_class_code,"""
    """tag_status_code,designed_by_company_name,production_critical,safety_critical
P-004,T-001,Inlet separator,U-100,SEP,IN_SVC,Demo Design Office,Y,N
P-004,T-002,Suction knock out drum,U-100,KOD,IN_SVC,Demo Design Office,Y,Y
P-004,T-003,Suction pressure transmitter,U-100,PT,IN_SVC,Demo Design Office,N,Y
P-004,T-004,Main lube oil pump,U-200,PUMP_C,IN_SVC,Demo Design Office,Y,N
P-004,T-005,Standby lube oil pump,U-200,PUMP_C,STANDBY,Demo Design Office,N,N
P-004,T-006,Recycle control valve,U-200,CV,IN_SVC,Demo Design Office,Y,Y
P-004,T-007,Discharge flow transmitter,,FT,IN_SVC,Demo Design Office,N,N
P-004,T-008,Unsupported demo class,U-200,WIDGET,IN_SVC,Demo Design Office,N,N
""",
}

EXPECTED_COUNTS = {
    "plants": 1,
    "process_units": 2,
    "tags": 6,
    "quarantined": 2,
}
EXPECTED_REASONS = {
    "process_unit_code is required and missing",
    "WIDGET is not a valid tag class",
}
SOURCE_ORDER = ("demo_plants", "demo_process_units", "demo_tags")


def fixture_rows(name: str) -> tuple[dict[str, str], ...]:
    """Parse one embedded fixture using the same rules as its README CSV."""
    return tuple(dict(row) for row in csv.DictReader(io.StringIO(FIXTURE_CSV[name])))


def _create_fixture_tables(spark: Any, catalog: str) -> None:
    from pyspark.sql.types import StringType, StructField, StructType

    spark.sql(
        f"CREATE SCHEMA IF NOT EXISTS {catalog}.bronze "
        "COMMENT 'Raw tables used by the Core v1 acceptance test.'"
    )
    for source in SOURCE_ORDER:
        rows = fixture_rows(source)
        columns = tuple(rows[0])
        schema = StructType([StructField(column, StringType(), True) for column in columns])
        frame = spark.createDataFrame(list(rows), schema=schema)
        frame.write.format("delta").mode("overwrite").option(
            "overwriteSchema", "true"
        ).saveAsTable(f"{catalog}.bronze.{source}")


def _entity_table(model: dict[str, Any], catalog: str, entity_name: str) -> str:
    entity = model["entities"][entity_name]
    return f"{catalog}.cfihos_{entity['subject_area']}.{entity_name}"


def _counts(spark: Any, catalog: str, model: dict[str, Any]) -> dict[str, int]:
    tables = {
        "plants": _entity_table(model, catalog, "plant"),
        "process_units": _entity_table(model, catalog, "process_unit"),
        "tags": _entity_table(model, catalog, "tag"),
        "quarantined": f"{catalog}.cfihos_quarantine.rows",
    }
    return {
        label: int(spark.sql(f"SELECT count(*) AS records FROM {table}").first().records)
        for label, table in tables.items()
    }


def _assert_fresh_catalog(spark: Any, catalog: str, model: dict[str, Any]) -> None:
    existing_inputs = [
        f"{catalog}.bronze.{source}"
        for source in SOURCE_ORDER
        if spark.catalog.tableExists(f"{catalog}.bronze.{source}")
    ]
    occupied: dict[str, int] = {}
    for entity_name in model["generation"]["spine_entities"]:
        table = _entity_table(model, catalog, entity_name)
        records = int(spark.sql(f"SELECT count(*) AS records FROM {table}").first().records)
        if records:
            occupied[table] = records
    quarantine = f"{catalog}.cfihos_quarantine.rows"
    quarantine_records = int(
        spark.sql(f"SELECT count(*) AS records FROM {quarantine}").first().records
    )
    if quarantine_records:
        occupied[quarantine] = quarantine_records
    load_audit = f"{catalog}.cfihos_ref.load_audit"
    if spark.catalog.tableExists(load_audit):
        audit_records = int(
            spark.sql(f"SELECT count(*) AS records FROM {load_audit}").first().records
        )
        if audit_records:
            occupied[load_audit] = audit_records
    if existing_inputs or occupied:
        details = []
        if existing_inputs:
            details.append("existing demo inputs: " + ", ".join(existing_inputs))
        if occupied:
            details.append(
                "non-empty core tables: "
                + ", ".join(f"{table}={records}" for table, records in occupied.items())
            )
        raise ValueError(
            "acceptance requires a fresh catalog and refuses to overwrite data; "
            + "; ".join(details)
        )


def _quarantine_reasons(spark: Any, catalog: str) -> list[str]:
    rows = spark.sql(
        f"SELECT explode(reasons) AS reason FROM {catalog}.cfihos_quarantine.rows"
    ).collect()
    return [row.reason for row in rows]


def _assert_expected(spark: Any, catalog: str, model: dict[str, Any]) -> dict[str, int]:
    counts = _counts(spark, catalog, model)
    if counts != EXPECTED_COUNTS:
        raise AssertionError(f"acceptance counts differ: expected {EXPECTED_COUNTS}, got {counts}")
    reasons = _quarantine_reasons(spark, catalog)
    if len(reasons) != 2 or set(reasons) != EXPECTED_REASONS:
        raise AssertionError(
            "acceptance quarantine reasons differ: "
            f"expected {sorted(EXPECTED_REASONS)}, got {sorted(reasons)}"
        )
    return counts


def run_acceptance(spark: Any, root: Path, catalog: str) -> dict[str, int]:
    """Deploy, load fixtures, conform twice, and prove exact idempotent results."""
    validate_identifier(catalog)
    model_path = root / "model" / "model.yml"
    model = yaml.safe_load(model_path.read_text(encoding="utf-8"))

    deploy(spark, root, catalog)
    _assert_fresh_catalog(spark, catalog, model)
    load_rdl(spark, root / "spec" / "rdl", catalog, "2.0")
    _create_fixture_tables(spark, catalog)

    print("Run order: plants -> process_units -> tags")
    for source in SOURCE_ORDER:
        conform(
            spark,
            catalog,
            root / "src" / "conform" / "sources" / f"{source}.yml",
            model_file=model_path,
        )
    first_counts = _assert_expected(spark, catalog, model)

    for source in SOURCE_ORDER:
        conform(
            spark,
            catalog,
            root / "src" / "conform" / "sources" / f"{source}.yml",
            model_file=model_path,
        )
    second_counts = _assert_expected(spark, catalog, model)
    if second_counts != first_counts:
        raise AssertionError(
            f"second conform run changed counts: before {first_counts}, after {second_counts}"
        )

    print(json.dumps(second_counts, sort_keys=True))
    return second_counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    args = parser.parse_args(argv)
    from pyspark.sql import SparkSession

    run_acceptance(SparkSession.builder.getOrCreate(), _SCRIPT_PATH.parents[1], args.catalog)
    return 0


if __name__ == "__main__":
    main()
