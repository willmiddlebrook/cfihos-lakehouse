"""Run the four executable v0.1 acceptance checks in a fresh deployed catalog."""

from __future__ import annotations

import argparse
import json
import sys
import time
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
                "spine_id": f"acceptance-{sequence}",
                "valid_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "valid_to": None,
                "is_current": True,
                "recorded_at": datetime.now(timezone.utc),
            }
        )
        rows.append(row)
    spark.createDataFrame(rows, schema=schema).write.mode("append").saveAsTable(table)


def _create_source_fixture(spark: Any, catalog: str) -> None:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.bronze")
    rows = [
        ("clean", "PLANT-A", "P-100", "Clean exact match", "OPERATING"),
        ("unknown-code", "PLANT-A", "P-100", "Blocked unknown code", "UNKNOWN"),
        (
            "variant-duplicate",
            "PLANT-A",
            "ASSET-P-100",
            "Ambiguous normalized match",
            "OPERATING",
        ),
    ]
    spark.createDataFrame(
        rows,
        "location_id string, plant_code string, functional_location_code string, "
        "description string, status string",
    ).write.mode("overwrite").saveAsTable(f"{catalog}.bronze.example_locations")


def _assert_count(spark: Any, table: str, condition: str, minimum: int = 1) -> int:
    count = spark.sql(f"SELECT count(*) AS records FROM {table} WHERE {condition}").first().records
    if count < minimum:
        raise AssertionError(f"expected at least {minimum} records in {table} where {condition}")
    return count


def _write_merge_event(spark: Any, catalog: str, event: dict[str, Any]) -> None:
    table = f"{catalog}.cfihos_trust.merge_audit"
    payload = {**event, "event_at": datetime.now(timezone.utc)}
    spark.createDataFrame([payload], schema=spark.table(table).schema).write.mode(
        "append"
    ).saveAsTable(table)


def _accept_merge_round_trip(spark: Any, catalog: str) -> None:
    try:
        from src.trust.merge_service import merge_state, unmerge_state
    except ModuleNotFoundError:
        from trust.merge_service import merge_state, unmerge_state

    table = f"{catalog}.cfihos_trust.id_map"
    spark.sql(f"DELETE FROM {table} WHERE source_system LIKE 'acceptance_merge_%'")
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
    fixture_maps = spark.table(table).filter("source_system LIKE 'acceptance_merge_%'")
    prior = [row.asDict() for row in fixture_maps.collect()]
    merged, merge_event = merge_state(
        prior, "acceptance-survivor", "acceptance-absorbed", "fixture", "acceptance merge"
    )
    spark.sql(
        f"UPDATE {table} SET spine_id = 'acceptance-survivor' "
        "WHERE spine_id = 'acceptance-absorbed' AND source_system = 'acceptance_merge_b'"
    )
    _write_merge_event(spark, catalog, merge_event)
    restored, unmerge_event = unmerge_state(merged, merge_event, "fixture", "acceptance unmerge")
    for row in restored:
        spark.sql(
            f"UPDATE {table} SET spine_id = '{row['spine_id']}' "
            f"WHERE source_system = '{row['source_system']}' AND source_id = '{row['source_id']}'"
        )
    _write_merge_event(spark, catalog, unmerge_event)
    after = [row.asDict() for row in fixture_maps.collect()]
    before_ids = sorted((row["source_system"], row["source_id"], row["spine_id"]) for row in prior)
    after_ids = sorted((row["source_system"], row["source_id"], row["spine_id"]) for row in after)
    if before_ids != after_ids:
        raise AssertionError("unmerge did not restore the prior ID map state")


def run(spark: Any, catalog: str, root: Path) -> dict[str, Any]:
    try:
        from src.onramp.engine import _sync_config, run_spark, validate_config
        from src.trust.who_wins import publish_claims
    except ModuleNotFoundError:
        from onramp.engine import _sync_config, run_spark, validate_config
        from trust.who_wins import publish_claims

    started = time.monotonic()
    model = yaml.safe_load((root / "model" / "model.yml").read_text(encoding="utf-8"))
    config_path = root / "src" / "onramp" / "sources" / "example_cmms.yml"
    raw_config = config_path.read_text(encoding="utf-8").replace("${catalog}", catalog)
    config = yaml.safe_load(raw_config)
    config["feeds"] = {"tag": config["feeds"]["tag"]}
    config["claims"] = {"tag.tag_status": config["claims"]["tag.tag_status"]}
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
    _seed_tag_candidates(spark, catalog)
    _create_source_fixture(spark, catalog)
    _sync_config(spark, catalog, config, raw_config)
    run_id = run_spark(spark, catalog, config, model)

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

    conflict_run = f"acceptance-conflict-{run_id}"
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
