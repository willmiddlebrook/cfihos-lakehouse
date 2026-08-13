"""Load all supplied Core RDL CSVs as versioned, inspectable Delta tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def sql_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not value or not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise ValueError(f"cannot create safe SQL name from {value!r}")
    return value


def rdl_table_name(path: Path) -> str:
    stem = re.sub(r"^CFIHOS CORE ", "", path.stem, flags=re.IGNORECASE)
    stem = re.sub(r" v\d+(?:\.\d+)*$", "", stem, flags=re.IGNORECASE)
    return sql_name(stem)


def decode_csv(path: Path) -> tuple[str, str]:
    payload = path.read_bytes()
    try:
        return payload.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        return payload.decode("cp1252"), "cp1252"


@dataclass(frozen=True)
class CsvException:
    file: str
    line: int
    reason: str
    raw_row: str


@dataclass(frozen=True)
class CsvBatch:
    table: str
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]
    exceptions: tuple[CsvException, ...]
    encoding: str


def parse_csv(path: Path) -> CsvBatch:
    text, encoding = decode_csv(path)
    stream = io.StringIO(text, newline="")
    reader = csv.reader(stream, strict=True)
    exceptions: list[CsvException] = []
    try:
        source_header = next(reader)
    except (StopIteration, csv.Error) as error:
        return CsvBatch(
            rdl_table_name(path),
            (),
            (),
            (CsvException(path.name, 1, f"header parse failed: {error}", ""),),
            encoding,
        )

    while source_header and not source_header[-1].strip():
        source_header.pop()
    columns = tuple(sql_name(value) for value in source_header)
    if len(columns) != len(set(columns)):
        raise ValueError(f"{path.name}: normalized CSV headers are not unique")

    rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for values in reader:
        line = reader.line_num
        while len(values) > len(columns) and not values[-1].strip():
            values.pop()
        if len(values) != len(columns):
            exceptions.append(
                CsvException(
                    path.name,
                    line,
                    f"expected {len(columns)} fields, found {len(values)}",
                    json.dumps(values, ensure_ascii=False),
                )
            )
            continue
        normalized = {column: value.strip() for column, value in zip(columns, values, strict=True)}
        fingerprint = "\x1f".join(normalized[column] for column in columns)
        normalized["_natural_key"] = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        if normalized["_natural_key"] in seen_keys:
            exceptions.append(
                CsvException(
                    path.name,
                    line,
                    f"duplicate natural key {normalized['_natural_key']}",
                    json.dumps(values, ensure_ascii=False),
                )
            )
            continue
        seen_keys.add(normalized["_natural_key"])
        rows.append(normalized)
    return CsvBatch(
        rdl_table_name(path),
        columns + ("_natural_key",),
        tuple(rows),
        tuple(exceptions),
        encoding,
    )


def load_rdl(spark: Any, spec_dir: Path, catalog: str, rdl_version: str) -> None:
    """Replace one RDL version atomically per table while retaining other versions."""
    from pyspark.sql import functions as F
    from pyspark.sql.types import StringType, StructField, StructType

    schema_name = f"{catalog}.cfihos_ref"
    spark.sql(
        f"CREATE SCHEMA IF NOT EXISTS {schema_name} "
        "COMMENT 'Versioned CFIHOS reference data; writable only by the RDL loader.'"
    )
    spark.sql(
        f"""CREATE TABLE IF NOT EXISTS {schema_name}.load_exceptions (
          exception_id STRING NOT NULL,
          rdl_version STRING NOT NULL,
          file STRING NOT NULL,
          line BIGINT NOT NULL,
          reason STRING NOT NULL,
          raw_row STRING,
          explained BOOLEAN NOT NULL,
          recorded_at TIMESTAMP NOT NULL
        ) USING DELTA
        COMMENT 'Rows rejected by the RDL loader; no parse failure is silently skipped.'"""
    )
    spark.sql(
        f"""CREATE TABLE IF NOT EXISTS {schema_name}.load_audit (
          rdl_version STRING NOT NULL,
          file STRING NOT NULL,
          table_name STRING NOT NULL,
          encoding STRING NOT NULL,
          source_rows BIGINT NOT NULL,
          loaded_rows BIGINT NOT NULL,
          exception_rows BIGINT NOT NULL,
          loaded_at TIMESTAMP NOT NULL
        ) USING DELTA
        COMMENT 'Per-file reconciliation evidence for each RDL load.'"""
    )
    files = sorted(spec_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"no RDL CSVs found in {spec_dir}")

    for path in files:
        batch = parse_csv(path)
        table = f"{schema_name}.`{batch.table}`"
        spark.sql(
            f"DELETE FROM {schema_name}.load_exceptions "
            f"WHERE rdl_version = '{rdl_version}' AND file = '{path.name}'"
        )
        spark.sql(
            f"DELETE FROM {schema_name}.load_audit "
            f"WHERE rdl_version = '{rdl_version}' AND file = '{path.name}'"
        )
        if spark.catalog.tableExists(table):
            spark.sql(f"DELETE FROM {table} WHERE rdl_version = '{rdl_version}'")

        if batch.rows:
            row_schema = StructType(
                [StructField(name, StringType(), True) for name in batch.columns]
            )
            frame = spark.createDataFrame(list(batch.rows), schema=row_schema)
            frame = frame.withColumn("rdl_version", F.lit(rdl_version)).withColumn(
                "loaded_at", F.current_timestamp()
            )
            frame.write.format("delta").mode("append").option(
                "mergeSchema", "true"
            ).saveAsTable(table)

        if batch.exceptions:
            exception_rows = [
                {
                    "exception_id": hashlib.sha256(
                        f"{rdl_version}|{item.file}|{item.line}|{item.reason}".encode()
                    ).hexdigest(),
                    "rdl_version": rdl_version,
                    "file": item.file,
                    "line": item.line,
                    "reason": item.reason,
                    "raw_row": item.raw_row,
                    "explained": item.reason.startswith("duplicate natural key"),
                }
                for item in batch.exceptions
            ]
            spark.createDataFrame(exception_rows).withColumn(
                "recorded_at", F.current_timestamp()
            ).write.mode("append").saveAsTable(f"{schema_name}.load_exceptions")

        audit = [{
            "rdl_version": rdl_version,
            "file": path.name,
            "table_name": batch.table,
            "encoding": batch.encoding,
            "source_rows": len(batch.rows) + len(batch.exceptions),
            "loaded_rows": len(batch.rows),
            "exception_rows": len(batch.exceptions),
        }]
        spark.createDataFrame(audit).withColumn("loaded_at", F.current_timestamp()).write.mode(
            "append"
        ).saveAsTable(f"{schema_name}.load_audit")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--rdl-version", default="2.0")
    parser.add_argument(
        "--spec-dir", type=Path, default=Path(__file__).resolve().parents[1] / "spec" / "rdl"
    )
    args = parser.parse_args(argv)
    from pyspark.sql import SparkSession

    load_rdl(SparkSession.builder.getOrCreate(), args.spec_dir, args.catalog, args.rdl_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
