"""Exercise dry-run prediction, rerun safety, registry creation, and stewardship."""

from __future__ import annotations

import argparse
import json
import sys
import time
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_SCRIPT_PATH = Path(globals().get("__file__", sys.argv[0])).resolve()


def _fixture_value(field: Any, sequence: int) -> Any:
    from pyspark.sql.types import (
        BooleanType,
        DateType,
        DoubleType,
        FloatType,
        IntegralType,
        StringType,
        TimestampType,
    )

    if isinstance(field.dataType, StringType):
        return f"fixture_{field.name}_{sequence}"
    if isinstance(field.dataType, BooleanType):
        return False
    if isinstance(field.dataType, DateType):
        return date(2026, 1, sequence)
    if isinstance(field.dataType, TimestampType):
        return datetime(2026, 1, sequence, tzinfo=timezone.utc)
    if isinstance(field.dataType, (IntegralType, FloatType, DoubleType)):
        return sequence
    raise TypeError(f"no fixture value for {field.name}: {field.dataType}")


def _seed_tag_candidates(spark: Any, catalog: str) -> None:
    table = f"{catalog}.cfihos_functional_asset.tag"
    spark.sql(f"DELETE FROM {table} WHERE spine_id LIKE 'acceptance-%'")
    schema = spark.table(table).schema
    rows = []
    for sequence, tag_name in ((1, "P-100"), (2, "LOC-P-100")):
        row = {field.name: _fixture_value(field, sequence) for field in schema}
        row.update(
            {
                "plant_code": "PLANT-A",
                "tag_name": tag_name,
                "tag_description": f"Acceptance candidate {sequence}",
                "tag_class_name": "ACCEPTANCE-TAG-CLASS",
                "spine_id": f"acceptance-{sequence}",
                "valid_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "valid_to": None,
                "is_current": True,
                "recorded_at": datetime.now(timezone.utc),
            }
        )
        rows.append(row)
    spark.createDataFrame(rows, schema=schema).write.mode("append").saveAsTable(table)


def _seed_classification_values(spark: Any, catalog: str) -> None:
    now = datetime.now(timezone.utc)
    fixtures = (
        (
            f"{catalog}.cfihos_classification.tag_class",
            "acceptance-tag-class",
            {"tag_class_name": "ACCEPTANCE-TAG-CLASS"},
        ),
        (
            f"{catalog}.cfihos_classification.equipment_class",
            "acceptance-equipment-class",
            {"equipment_class_name": "ACCEPTANCE-EQUIPMENT-CLASS"},
        ),
    )
    for table, spine_id, values in fixtures:
        spark.sql(f"DELETE FROM {table} WHERE spine_id = '{spine_id}'")
        schema = spark.table(table).schema
        row = {field.name: _fixture_value(field, 1) for field in schema}
        row.update(
            {
                **values,
                "spine_id": spine_id,
                "valid_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "valid_to": None,
                "is_current": True,
                "recorded_at": now,
            }
        )
        spark.createDataFrame([row], schema=schema).write.mode("append").saveAsTable(table)


def _create_source_fixture(spark: Any, catalog: str) -> None:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.bronze")
    rows = [
        (
            "clean",
            "PLANT-A",
            "P-100",
            "Clean exact match",
            "OPERATING",
            "UNIT-A",
            "ACCEPTANCE-TAG-CLASS",
            "DESIGN-A",
            True,
            False,
        ),
        (
            "unknown-code",
            "PLANT-A",
            "P-100",
            "Blocked unknown code",
            "UNKNOWN",
            "UNIT-A",
            "ACCEPTANCE-TAG-CLASS",
            "DESIGN-A",
            True,
            False,
        ),
        (
            "variant-duplicate",
            "PLANT-A",
            "ASSET-P-100",
            "Ambiguous normalized match",
            "OPERATING",
            "UNIT-A",
            "ACCEPTANCE-TAG-CLASS",
            "DESIGN-A",
            True,
            False,
        ),
    ]
    spark.createDataFrame(
        rows,
        "location_id string, plant_code string, functional_location_code string, "
        "description string, status string, process_unit_code string, tag_class_name string, "
        "designed_by_company_name string, production_critical_item_indicator boolean, "
        "safety_critical_item_indicator boolean",
    ).write.mode("overwrite").saveAsTable(f"{catalog}.bronze.example_locations")


def _create_equipment_fixture(spark: Any, catalog: str) -> None:
    rows = [
        (
            "founding-complete",
            "EQ-100",
            "SN-100",
            "ACCEPTANCE-EQUIPMENT-CLASS",
            "2024-01-15",
        ),
        ("founding-missing", "EQ-200", "SN-200", None, "2024-02-20"),
        (
            "founding-invalid",
            "EQ-300",
            "SN-300",
            "ACCEPTANCE-EQUIPMENT-CLASS",
            "not-a-date",
        ),
    ]
    spark.createDataFrame(
        rows,
        "asset_id string, asset_code string, serial_number string, class_name string, "
        "installed_on string",
    ).write.mode("overwrite").saveAsTable(f"{catalog}.bronze.example_assets")


def _assert_count(spark: Any, table: str, condition: str, minimum: int = 1) -> int:
    count = spark.sql(f"SELECT count(*) AS records FROM {table} WHERE {condition}").first().records
    if count < minimum:
        raise AssertionError(f"expected at least {minimum} records in {table} where {condition}")
    return count


def _count(spark: Any, table: str, condition: str = "true") -> int:
    return int(
        spark.sql(f"SELECT count(*) AS records FROM {table} WHERE {condition}").first().records
    )


def _source_surface_counts(spark: Any, catalog: str, source: str) -> dict[str, int]:
    return {
        "id_map": _count(
            spark,
            f"{catalog}.cfihos_trust.id_map",
            f"source_system = '{source}'",
        ),
        "review_queue": _count(
            spark,
            f"{catalog}.cfihos_trust.review_queue",
            f"source_system = '{source}'",
        ),
        "unmapped_codes": _count(
            spark,
            f"{catalog}.cfihos_onramp.unmapped_codes",
            f"source = '{source}'",
        ),
        "staged_claims": _count(
            spark,
            f"{catalog}.cfihos_onramp.staged_claims",
            f"source_system = '{source}'",
        ),
    }


def _accept_merge_round_trip(spark: Any, catalog: str) -> None:
    try:
        from src.trust.steward import apply_merge, apply_unmerge
    except ModuleNotFoundError:
        from trust.steward import apply_merge, apply_unmerge

    table = f"{catalog}.cfihos_trust.id_map"
    spark.sql(f"DELETE FROM {table} WHERE source_system LIKE 'acceptance_merge_%'")
    spark.sql(
        f"DELETE FROM {catalog}.cfihos_trust.merge_audit "
        "WHERE survivor_spine_id = 'acceptance-survivor'"
    )
    now = datetime.now(timezone.utc)
    seed = [
        ("acceptance_merge_a", "tag", "A", "acceptance-survivor", "steward", now, "fixture"),
        ("acceptance_merge_b", "tag", "B", "acceptance-absorbed", "steward", now, "fixture"),
    ]
    spark.createDataFrame(
        seed,
        "source_system string, entity string, source_id string, spine_id string, "
        "match_tier string, matched_at timestamp, matched_by string",
    ).write.mode("append").saveAsTable(table)
    prior = [
        row.asDict()
        for row in spark.table(table).filter("source_system LIKE 'acceptance_merge_%'").collect()
    ]
    merge_event_id = apply_merge(
        spark,
        catalog,
        "acceptance-survivor",
        "acceptance-absorbed",
        "fixture",
        "acceptance merge",
    )
    apply_unmerge(
        spark, catalog, merge_event_id, "fixture", "acceptance unmerge"
    )
    after = [
        row.asDict()
        for row in spark.table(table).filter("source_system LIKE 'acceptance_merge_%'").collect()
    ]
    before_ids = sorted((row["source_system"], row["source_id"], row["spine_id"]) for row in prior)
    after_ids = sorted((row["source_system"], row["source_id"], row["spine_id"]) for row in after)
    if before_ids != after_ids:
        raise AssertionError("unmerge did not restore the prior ID map state")


def run(spark: Any, catalog: str, root: Path) -> dict[str, Any]:
    try:
        from src.onramp.engine import _sync_config, run_spark, validate_config
        from src.trust.spine_ids import mint_spine_id
        from src.trust.who_wins import publish_claims
        from src.validate import validate
    except ModuleNotFoundError:
        from onramp.engine import _sync_config, run_spark, validate_config
        from trust.spine_ids import mint_spine_id
        from trust.who_wins import publish_claims
        from validate import validate

    started = time.monotonic()
    model = yaml.safe_load((root / "model" / "model.yml").read_text(encoding="utf-8"))
    config_path = root / "src" / "onramp" / "sources" / "example_cmms.yml"
    raw_config = config_path.read_text(encoding="utf-8").replace("${catalog}", catalog)
    base_config = yaml.safe_load(raw_config)
    config = deepcopy(base_config)
    config["origination"] = "steward_only"
    config["feeds"] = {"tag": config["feeds"]["tag"]}
    config["claims"] = {
        key: value for key, value in config["claims"].items() if key.startswith("tag.")
    }
    config["value_maps"] = {"tag.tag_status": config["value_maps"]["tag.tag_status"]}
    errors = validate_config(config, model)
    if errors:
        raise AssertionError(errors)

    spark.sql(f"DELETE FROM {catalog}.cfihos_trust.id_map WHERE source_system = 'example_cmms'")
    spark.sql(
        f"DELETE FROM {catalog}.cfihos_trust.review_queue "
        "WHERE source_system = 'example_cmms'"
    )
    spark.sql(f"DELETE FROM {catalog}.cfihos_onramp.unmapped_codes WHERE source = 'example_cmms'")
    spark.sql(
        f"DELETE FROM {catalog}.cfihos_onramp.staged_claims "
        "WHERE source_system = 'example_cmms'"
    )
    spark.sql(
        f"DELETE FROM {catalog}.cfihos_trust.published_attributes "
        "WHERE spine_id LIKE 'acceptance-%'"
    )
    spark.sql(
        f"DELETE FROM {catalog}.cfihos_trust.pending_records "
        "WHERE spine_id LIKE 'acceptance-%'"
    )
    _seed_classification_values(spark, catalog)
    _seed_tag_candidates(spark, catalog)
    _create_source_fixture(spark, catalog)
    _sync_config(spark, catalog, config, raw_config)
    before_dry_run = _source_surface_counts(spark, catalog, "example_cmms")
    dry_report = run_spark(spark, catalog, config, model, dry_run=True)
    after_dry_run = _source_surface_counts(spark, catalog, "example_cmms")
    if after_dry_run != before_dry_run:
        raise AssertionError("dry run changed a trust or on-ramp table")
    live_report = run_spark(spark, catalog, config, model)
    run_id = live_report["run_id"]
    after_live_run = _source_surface_counts(spark, catalog, "example_cmms")
    predicted = dry_report["entities"]["tag"]
    observed = {
        "exact": after_live_run["id_map"] - before_dry_run["id_map"],
        "queued": after_live_run["review_queue"] - before_dry_run["review_queue"],
        "blocked_rows": after_live_run["unmapped_codes"] - before_dry_run["unmapped_codes"],
    }
    for metric, actual in observed.items():
        if predicted[metric] != actual:
            raise AssertionError(
                f"dry run predicted {metric}={predicted[metric]}, observed {actual}"
            )

    stable_before_rerun = {
        key: after_live_run[key] for key in ("id_map", "review_queue", "unmapped_codes")
    }
    run_spark(spark, catalog, config, model)
    stable_after_rerun = _source_surface_counts(spark, catalog, "example_cmms")
    if stable_before_rerun != {
        key: stable_after_rerun[key]
        for key in ("id_map", "review_queue", "unmapped_codes")
    }:
        raise AssertionError("rerun changed id_map, review_queue, or unmapped_codes counts")

    results = {
        "exact_matches": _assert_count(
            spark,
            f"{catalog}.cfihos_trust.id_map",
            "source_system = 'example_cmms' AND match_tier = 'exact'",
        ),
        "unmapped_codes": _assert_count(
            spark,
            f"{catalog}.cfihos_onramp.unmapped_codes",
            f"run_id = '{run_id}' AND source_value = 'UNKNOWN'",
        ),
        "review_records": _assert_count(
            spark,
            f"{catalog}.cfihos_trust.review_queue",
            f"run_id = '{run_id}' AND status = 'open'",
        ),
    }

    founding_config = deepcopy(base_config)
    founding_config["feeds"] = {"equipment": founding_config["feeds"]["equipment"]}
    founding_config["claims"] = {
        key: value
        for key, value in founding_config["claims"].items()
        if key.startswith("equipment.")
    }
    founding_config["value_maps"] = {}
    founding_errors = validate_config(founding_config, model)
    if founding_errors:
        raise AssertionError(founding_errors)
    founding_source_ids = ("founding-complete", "founding-missing", "founding-invalid")
    founding_spine_ids = {
        source_id: mint_spine_id("equipment", "example_cmms", source_id)
        for source_id in founding_source_ids
    }
    spine_id_sql = ", ".join(f"'{value}'" for value in founding_spine_ids.values())
    spark.sql(
        f"DELETE FROM {catalog}.cfihos_trust.id_map "
        "WHERE source_system = 'example_cmms' AND entity = 'equipment'"
    )
    spark.sql(
        f"DELETE FROM {catalog}.cfihos_trust.published_attributes "
        f"WHERE spine_id IN ({spine_id_sql})"
    )
    spark.sql(
        f"DELETE FROM {catalog}.cfihos_trust.pending_records "
        f"WHERE spine_id IN ({spine_id_sql})"
    )
    spark.sql(
        f"DELETE FROM {catalog}.cfihos_physical_asset.equipment "
        f"WHERE spine_id IN ({spine_id_sql})"
    )
    _create_equipment_fixture(spark, catalog)
    founding_before = _source_surface_counts(spark, catalog, "example_cmms")
    founding_dry = run_spark(spark, catalog, founding_config, model, dry_run=True)
    if _source_surface_counts(spark, catalog, "example_cmms") != founding_before:
        raise AssertionError("founding dry run changed a trust or on-ramp table")
    founding_live = run_spark(spark, catalog, founding_config, model)
    founding_after = _source_surface_counts(spark, catalog, "example_cmms")
    would_found = founding_dry["entities"]["equipment"]["would_found"]
    founded_rows = founding_after["id_map"] - founding_before["id_map"]
    if would_found != founded_rows:
        raise AssertionError(
            f"founding dry run predicted {would_found} rows, observed {founded_rows}"
        )
    if founding_dry["entities"]["equipment"]["queued"]:
        raise AssertionError("founding dry run counted would-found rows as queued")
    results["founded_records"] = _assert_count(
        spark,
        f"{catalog}.cfihos_trust.id_map",
        "source_system = 'example_cmms' AND entity = 'equipment' "
        "AND match_tier = 'founding'",
        3,
    )
    complete_spine = founding_spine_ids["founding-complete"]
    results["materialized_records"] = _assert_count(
        spark,
        f"{catalog}.cfihos_physical_asset.equipment",
        f"spine_id = '{complete_spine}' AND is_current",
    )
    for source_id in ("founding-missing", "founding-invalid"):
        spine_id = founding_spine_ids[source_id]
        if _count(
            spark,
            f"{catalog}.cfihos_physical_asset.equipment",
            f"spine_id = '{spine_id}'",
        ):
            raise AssertionError(f"pending spine {spine_id} reached the entity table")
    results["pending_missing"] = _assert_count(
        spark,
        f"{catalog}.cfihos_trust.pending_records",
        f"spine_id = '{founding_spine_ids['founding-missing']}' "
        "AND reason = 'missing' AND array_contains(missing_attributes, 'equipment_class_name')",
    )
    results["pending_invalid"] = _assert_count(
        spark,
        f"{catalog}.cfihos_trust.pending_records",
        f"spine_id = '{founding_spine_ids['founding-invalid']}' "
        "AND reason = 'invalid_value' "
        "AND array_contains(missing_attributes, 'equipment_actual_installation_date')",
    )
    versions_before = _count(
        spark,
        f"{catalog}.cfihos_physical_asset.equipment",
        f"spine_id = '{complete_spine}'",
    )
    stable_founding_before = {
        key: founding_after[key] for key in ("id_map", "review_queue", "unmapped_codes")
    }
    run_spark(spark, catalog, founding_config, model)
    stable_founding_after = _source_surface_counts(spark, catalog, "example_cmms")
    if stable_founding_before != {
        key: stable_founding_after[key]
        for key in ("id_map", "review_queue", "unmapped_codes")
    }:
        raise AssertionError("founding rerun changed stable crosswalk or exception counts")
    if _count(
        spark,
        f"{catalog}.cfihos_physical_asset.equipment",
        f"spine_id = '{complete_spine}'",
    ) != versions_before:
        raise AssertionError("founding rerun created spurious SCD2 history")
    if _count(
        spark,
        f"{catalog}.cfihos_physical_asset.equipment",
        f"spine_id = '{complete_spine}' AND is_current",
    ) != 1:
        raise AssertionError("founding rerun produced duplicate current entity rows")

    generation_report = yaml.safe_load(
        (root / "model" / "generation_report.yml").read_text(encoding="utf-8")
    )
    validation_results = validate(spark, catalog, model, generation_report)
    checks = {item["check_name"]: item for item in validation_results}
    expected_checks = {"id_map_unique", "table_comments", "pending_records"}
    if not expected_checks <= checks.keys() or not any(
        name.startswith("fk_orphans_") for name in checks
    ):
        raise AssertionError("new constraint checks are missing from validation_results")
    if checks["id_map_unique"]["status"] != "PASS":
        raise AssertionError("id_map_unique failed after an idempotent rerun")
    failed_checks = [item for item in validation_results if item["status"] == "FAIL"]
    if failed_checks:
        raise AssertionError(f"acceptance validation failures: {failed_checks}")
    results["validation_checks"] = len(validation_results)

    conflict_run = f"acceptance-conflict-{founding_live['run_id']}"
    claims = [
        (conflict_run, "source_a", "tag", "acceptance-conflict", "tag_status", "ACTIVE", 1, now)
        for now in [datetime.now(timezone.utc)]
    ] + [
        (
            conflict_run,
            "source_b",
            "tag",
            "acceptance-conflict",
            "tag_status",
            "INACTIVE",
            1,
            datetime.now(timezone.utc),
        )
    ]
    spark.createDataFrame(
        claims,
        "run_id string, source_system string, entity string, spine_id string, attribute string, "
        "value string, wins_rank int, observed_at timestamp",
    ).write.mode("append").saveAsTable(f"{catalog}.cfihos_onramp.staged_claims")
    publish_claims(spark, catalog, conflict_run)
    results["tied_conflicts"] = _assert_count(
        spark,
        f"{catalog}.cfihos_trust.attribute_conflicts",
        f"run_id = '{conflict_run}' AND conflict_type = 'tied_rank'",
        2,
    )
    published_tie = spark.sql(
        f"SELECT count(*) records FROM {catalog}.cfihos_trust.published_attributes "
        "WHERE spine_id = 'acceptance-conflict' AND attribute = 'tag_status' AND is_current"
    ).first().records
    if published_tie:
        raise AssertionError("a tied claim reached the published spine")

    _accept_merge_round_trip(spark, catalog)
    results["merge_events"] = _assert_count(
        spark,
        f"{catalog}.cfihos_trust.merge_audit",
        "survivor_spine_id = 'acceptance-survivor'",
        2,
    )
    results["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    args = parser.parse_args()
    from pyspark.sql import SparkSession

    results = run(
        SparkSession.builder.getOrCreate(), args.catalog, _SCRIPT_PATH.parents[1]
    )
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    main()
