"""Materialize current winning attributes into canonical SCD2 registry tables."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date, datetime
from math import isfinite
from typing import Any

try:
    from src.identifiers import validate_identifier
except ModuleNotFoundError:  # Serverless Python-file tasks put src/ on sys.path.
    from identifiers import validate_identifier


def required_attributes(entity: dict[str, Any]) -> tuple[str, ...]:
    """Return the attributes whose absence makes a canonical row invalid."""
    return tuple(
        item["name"]
        for item in entity["attributes"]
        if item["requirement"] in {"identifier", "mandatory"}
    )


def pivot_attributes(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Pure equivalent of the publication pivot, used to test its semantics."""
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        record = output.setdefault(row["spine_id"], {"spine_id": row["spine_id"]})
        attribute = row["attribute"]
        if attribute in record:
            raise ValueError(f"multiple current values for {row['spine_id']}.{attribute}")
        record[attribute] = row.get("value")
    return output


def record_changed(
    current: dict[str, Any] | None,
    candidate: dict[str, Any],
    attributes: Iterable[str],
) -> bool:
    """Compare canonical values with Python's null-safe equality semantics."""
    if current is None:
        return True
    return any(current.get(name) != candidate.get(name) for name in attributes)


def missing_required(
    candidate: dict[str, Any], required: Iterable[str]
) -> tuple[str, ...]:
    """Identify every required canonical value missing from a candidate row."""
    return tuple(name for name in required if candidate.get(name) is None)


def cast_attribute_value(value: Any, datatype: str) -> Any:
    """Pure strict cast used to prove invalid values do not become silent nulls."""
    if value is None:
        return None
    normalized_type = datatype.upper()
    try:
        if normalized_type == "STRING":
            return str(value)
        if normalized_type == "BOOLEAN":
            normalized = str(value).strip().casefold()
            if normalized not in {"true", "false"}:
                raise ValueError
            return normalized == "true"
        if normalized_type in {"BIGINT", "INT", "INTEGER"}:
            normalized = str(value).strip()
            if not normalized or any(character in normalized for character in ".eE"):
                raise ValueError
            return int(normalized)
        if normalized_type in {"DOUBLE", "FLOAT"}:
            result = float(str(value).strip())
            if not isfinite(result):
                raise ValueError
            return result
        if normalized_type == "DATE":
            return date.fromisoformat(str(value).strip())
        if normalized_type == "TIMESTAMP":
            return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid {normalized_type} value: {value!r}") from error
    raise ValueError(f"unsupported model datatype: {datatype}")


def pending_replace_predicate(entity_name: str) -> str:
    """Return the safe Delta predicate used to replace one current pending slice."""
    return f"entity = '{validate_identifier(entity_name)}'"


def _target_table(catalog: str, entity: dict[str, Any]) -> str:
    return f"{catalog}.cfihos_{entity['subject_area']}.{entity['name']}"


def materialize_entities(
    spark: Any,
    catalog: str,
    model: dict[str, Any],
    entity_names: Iterable[str],
) -> None:
    """Apply current published attributes to each fed entity's canonical table."""
    from pyspark.sql import functions as F

    validate_identifier(catalog)
    pending_table = f"{catalog}.cfihos_trust.pending_records"
    for entity_name in dict.fromkeys(entity_names):
        entity = model["entities"][entity_name]
        attributes = [item["name"] for item in entity["attributes"]]
        mandatory = required_attributes(entity)
        published = spark.table(f"{catalog}.cfihos_trust.published_attributes").filter(
            (F.col("entity") == entity_name) & F.col("is_current")
        )
        candidates = published.groupBy("spine_id").pivot("attribute", attributes).agg(
            F.first("value")
        )
        presence = (
            published.withColumn("_present", F.lit(True))
            .groupBy("spine_id")
            .pivot("attribute", attributes)
            .agg(F.first("_present"))
            .select(
                "spine_id",
                *[
                    F.coalesce(F.col(name), F.lit(False)).alias(f"_present_{name}")
                    for name in attributes
                ],
            )
        )
        candidates = candidates.join(presence, "spine_id", "inner")

        typed = candidates
        for item in entity["attributes"]:
            escaped_name = item["name"].replace("`", "``")
            typed = typed.withColumn(
                f"_typed_{item['name']}",
                F.expr(f"try_cast(`{escaped_name}` AS {item['datatype']})"),
            )
        missing_values = F.array(
            *[
                F.when(
                    ~F.col(f"_present_{name}") | F.col(name).isNull(), F.lit(name)
                ).otherwise(F.lit(None).cast("string"))
                for name in mandatory
            ]
        )
        invalid_values = F.array(
            *[
                F.when(
                    F.col(f"_present_{item['name']}")
                    & F.col(item["name"]).isNotNull()
                    & F.col(f"_typed_{item['name']}").isNull(),
                    F.lit(item["name"]),
                ).otherwise(F.lit(None).cast("string"))
                for item in entity["attributes"]
            ]
        )
        typed = typed.withColumn(
            "_missing_attributes", F.filter(missing_values, lambda value: value.isNotNull())
        ).withColumn(
            "_invalid_attributes", F.filter(invalid_values, lambda value: value.isNotNull())
        )
        missing = typed.filter(F.size("_missing_attributes") > 0).select(
            "spine_id",
            F.lit(entity_name).alias("entity"),
            F.col("_missing_attributes").alias("missing_attributes"),
            F.lit("missing").alias("reason"),
            F.current_timestamp().alias("recorded_at"),
        )
        invalid = typed.filter(F.size("_invalid_attributes") > 0).select(
            "spine_id",
            F.lit(entity_name).alias("entity"),
            F.col("_invalid_attributes").alias("missing_attributes"),
            F.lit("invalid_value").alias("reason"),
            F.current_timestamp().alias("recorded_at"),
        )
        incomplete = missing.unionByName(invalid)
        complete = typed.filter(
            (F.size("_missing_attributes") == 0) & (F.size("_invalid_attributes") == 0)
        )
        typed_rows = complete.select(
            "spine_id",
            *[
                F.col(f"_typed_{item['name']}").alias(item["name"])
                for item in entity["attributes"]
            ],
            *[F.col(f"_present_{name}") for name in attributes],
        )
        target_table = _target_table(catalog, entity)
        current = spark.table(target_table).filter(F.col("is_current"))
        current_values = current.select(
            F.col("spine_id").alias("_current_spine_id"),
            *[F.col(name).alias(f"_current_{name}") for name in attributes],
        )
        joined = typed_rows.join(
            current_values,
            typed_rows.spine_id == current_values._current_spine_id,
            "left",
        )
        materialized = joined.select(
            typed_rows["spine_id"],
            *[
                F.when(F.col(f"_present_{name}"), F.col(name))
                .otherwise(F.col(f"_current_{name}"))
                .alias(name)
                for name in attributes
            ],
            "_current_spine_id",
            *[F.col(f"_current_{name}") for name in attributes],
        )
        differences = [
            ~F.col(name).eqNullSafe(F.col(f"_current_{name}")) for name in attributes
        ]
        differs = differences[0]
        for condition in differences[1:]:
            differs = differs | condition
        changed = materialized.filter(
            F.col("_current_spine_id").isNotNull() & differs
        ).select(materialized["spine_id"], *[materialized[name] for name in attributes])
        additions = materialized.filter(F.col("_current_spine_id").isNull()).select(
            "spine_id", *attributes
        )
        inserts = additions.unionByName(changed)

        change_view = f"cfihos_materialize_changes_{uuid.uuid4().hex}"
        changed.select("spine_id").distinct().createOrReplaceTempView(change_view)
        spark.sql(
            f"""MERGE INTO {target_table} target
            USING {change_view} source
            ON target.spine_id = source.spine_id AND target.is_current = true
            WHEN MATCHED THEN UPDATE SET
              target.valid_to = current_timestamp(), target.is_current = false"""
        )
        target_schema = spark.table(target_table).schema
        ready = (
            inserts.withColumn("valid_from", F.current_timestamp())
            .withColumn("valid_to", F.lit(None).cast("timestamp"))
            .withColumn("is_current", F.lit(True))
            .withColumn("recorded_at", F.current_timestamp())
        )
        ready.select(
            *[F.col(field.name).cast(field.dataType).alias(field.name) for field in target_schema]
        ).write.mode("append").saveAsTable(target_table)

        # pending_records is the current work pile, not an append-only history table.
        # Update it only after the canonical writes succeed. A failure can therefore
        # leave a conservative stale pending item, but can never clear one early.
        incomplete.write.mode("overwrite").option(
            "replaceWhere", pending_replace_predicate(entity_name)
        ).saveAsTable(pending_table)
