"""Runnable, audited steward decisions around pure state transitions."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any

import yaml

try:
    from src.identifiers import validate_identifier
    from src.trust.merge_service import merge_state, unmerge_state
    from src.trust.spine_ids import mint_spine_id
except ModuleNotFoundError:  # Serverless Python-file tasks put src/ on sys.path.
    from identifiers import validate_identifier
    from trust.merge_service import merge_state, unmerge_state
    from trust.spine_ids import mint_spine_id

_SCRIPT_PATH = Path(globals().get("__file__", sys.argv[0])).resolve()


def _require_open(queue_row: dict[str, Any]) -> None:
    if queue_row.get("status") != "open":
        raise ValueError(f"queue item {queue_row.get('queue_id')} is not open")


def confirm_to_existing_state(
    queue_row: dict[str, Any],
    spine_id: str,
    actor: str,
    resolved_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve an open queue item to a steward-selected existing spine ID."""
    _require_open(queue_row)
    if not spine_id or not actor:
        raise ValueError("spine_id and actor are required")
    timestamp = resolved_at or datetime.now(timezone.utc)
    resolved = {
        **queue_row,
        "candidate_spine_id": spine_id,
        "status": "confirmed",
        "resolved_by": actor,
        "resolved_at": timestamp,
    }
    mapping = {
        "source_system": queue_row["source_system"],
        "entity": queue_row["entity"],
        "source_id": queue_row["source_id"],
        "spine_id": spine_id,
        "match_tier": "steward",
        "matched_at": timestamp,
        "matched_by": actor,
    }
    return resolved, mapping


def confirm_as_new_state(
    queue_row: dict[str, Any],
    actor: str,
    resolved_at: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve an open queue item by deterministically originating a spine ID."""
    spine_id = mint_spine_id(
        queue_row["entity"], queue_row["source_system"], queue_row["source_id"]
    )
    return confirm_to_existing_state(queue_row, spine_id, actor, resolved_at)


def reject_state(
    queue_row: dict[str, Any],
    actor: str,
    reason: str,
    resolved_at: datetime | None = None,
) -> dict[str, Any]:
    """Make a final rejection decision; rejected items intentionally never requeue."""
    _require_open(queue_row)
    if not actor or not reason:
        raise ValueError("actor and reason are required")
    return {
        **queue_row,
        "reason": reason,
        "status": "rejected",
        "resolved_by": actor,
        "resolved_at": resolved_at or datetime.now(timezone.utc),
    }


def _queue_row(spark: Any, catalog: str, queue_id: str) -> dict[str, Any]:
    from pyspark.sql import functions as F

    rows = (
        spark.table(f"{catalog}.cfihos_trust.review_queue")
        .filter(F.col("queue_id") == queue_id)
        .limit(2)
        .collect()
    )
    if len(rows) != 1:
        raise ValueError(f"expected one queue item for {queue_id}, found {len(rows)}")
    return rows[0].asDict(recursive=True)


def _apply_queue_update(spark: Any, catalog: str, row: dict[str, Any]) -> None:
    view = f"cfihos_queue_update_{uuid.uuid4().hex}"
    table = f"{catalog}.cfihos_trust.review_queue"
    spark.createDataFrame([row], schema=spark.table(table).schema).createOrReplaceTempView(view)
    spark.sql(
        f"""MERGE INTO {table} target USING {view} source
        ON target.queue_id = source.queue_id
        WHEN MATCHED THEN UPDATE SET
          target.candidate_spine_id = source.candidate_spine_id,
          target.reason = source.reason,
          target.status = source.status,
          target.resolved_by = source.resolved_by,
          target.resolved_at = source.resolved_at"""
    )


def _append_mapping(spark: Any, catalog: str, mapping: dict[str, Any]) -> None:
    from pyspark.sql import functions as F

    table = f"{catalog}.cfihos_trust.id_map"
    duplicate = spark.table(table).filter(
        (F.col("source_system") == mapping["source_system"])
        & (F.col("entity") == mapping["entity"])
        & (F.col("source_id") == mapping["source_id"])
    )
    if duplicate.limit(1).count():
        raise ValueError("source identifier already has a spine mapping")
    spark.createDataFrame([mapping], schema=spark.table(table).schema).write.mode(
        "append"
    ).saveAsTable(table)


@cache
def _entity_subject_area(entity: str) -> str:
    """Resolve a canonical entity to its generated subject-area schema."""
    validate_identifier(entity)
    model_path = _SCRIPT_PATH.parents[2] / "model" / "model.yml"
    model = yaml.safe_load(model_path.read_text(encoding="utf-8"))
    entity_config = model.get("entities", {}).get(entity) if isinstance(model, dict) else None
    if not isinstance(entity_config, dict):
        raise ValueError(f"target entity {entity!r} is not present in model.yml")
    subject_area = entity_config.get("subject_area")
    if not isinstance(subject_area, str):
        raise ValueError(f"target entity {entity!r} has no subject area in model.yml")
    return validate_identifier(subject_area)


def _require_existing_spine(
    spark: Any, catalog: str, entity: str, spine_id: str
) -> None:
    """Fail before mutation unless the spine is a current row of the target entity."""
    subject_area = _entity_subject_area(entity)
    table = f"{catalog}.cfihos_{subject_area}.{entity}"
    requested = spark.createDataFrame([(spine_id,)], "spine_id string")
    exists = (
        spark.table(table)
        .filter("is_current = true")
        .join(requested, "spine_id", "inner")
        .limit(1)
        .count()
    )
    if not exists:
        raise ValueError(
            f"spine_id {spine_id!r} does not exist for target entity {entity!r}"
        )


def confirm_to_existing(
    spark: Any, catalog: str, queue_id: str, spine_id: str, actor: str
) -> str:
    validate_identifier(catalog)
    resolved, mapping = confirm_to_existing_state(
        _queue_row(spark, catalog, queue_id), spine_id, actor
    )
    _require_existing_spine(spark, catalog, mapping["entity"], spine_id)
    _append_mapping(spark, catalog, mapping)
    _apply_queue_update(spark, catalog, resolved)
    return spine_id


def confirm_as_new(spark: Any, catalog: str, queue_id: str, actor: str) -> str:
    """Confirm as new; rerun the source so its claims flow through the direct mapping."""
    validate_identifier(catalog)
    resolved, mapping = confirm_as_new_state(_queue_row(spark, catalog, queue_id), actor)
    _append_mapping(spark, catalog, mapping)
    _apply_queue_update(spark, catalog, resolved)
    return mapping["spine_id"]


def reject(
    spark: Any, catalog: str, queue_id: str, actor: str, reason: str
) -> None:
    validate_identifier(catalog)
    _apply_queue_update(
        spark, catalog, reject_state(_queue_row(spark, catalog, queue_id), actor, reason)
    )


def _audit_event(spark: Any, catalog: str, event: dict[str, Any]) -> None:
    table = f"{catalog}.cfihos_trust.merge_audit"
    payload = dict(event)
    if isinstance(payload["event_at"], str):
        payload["event_at"] = datetime.fromisoformat(payload["event_at"])
    spark.createDataFrame([payload], schema=spark.table(table).schema).write.mode(
        "append"
    ).saveAsTable(table)


def _apply_id_map_rows(spark: Any, catalog: str, rows: list[dict[str, Any]]) -> None:
    table = f"{catalog}.cfihos_trust.id_map"
    view = f"cfihos_id_map_update_{uuid.uuid4().hex}"
    updates = [
        (row["source_system"], row["entity"], row["source_id"], row["spine_id"])
        for row in rows
    ]
    spark.createDataFrame(
        updates,
        "source_system string, entity string, source_id string, spine_id string",
    ).createOrReplaceTempView(view)
    spark.sql(
        f"""MERGE INTO {table} target USING {view} source
        ON target.source_system = source.source_system
          AND target.entity = source.entity
          AND target.source_id = source.source_id
        WHEN MATCHED THEN UPDATE SET target.spine_id = source.spine_id"""
    )


def _require_merge_survivor(
    spark: Any, catalog: str, survivor: str, affected: list[dict[str, Any]]
) -> None:
    """Require the survivor to be current for every entity the merge will rewrite."""
    for entity in sorted({row["entity"] for row in affected}):
        _require_existing_spine(spark, catalog, entity, survivor)


def apply_merge(
    spark: Any,
    catalog: str,
    survivor: str,
    absorbed: str,
    actor: str,
    reason: str,
) -> str:
    validate_identifier(catalog)
    absorbed_key = spark.createDataFrame([(absorbed,)], "spine_id string")
    affected = [
        row.asDict(recursive=True)
        for row in spark.table(f"{catalog}.cfihos_trust.id_map")
        .join(absorbed_key, "spine_id", "inner")
        .collect()
    ]
    updated, event = merge_state(affected, survivor, absorbed, actor, reason)
    _require_merge_survivor(spark, catalog, survivor, affected)
    _apply_id_map_rows(spark, catalog, updated)
    _audit_event(spark, catalog, event)
    return event["event_id"]


def apply_unmerge(
    spark: Any, catalog: str, merge_event_id: str, actor: str, reason: str
) -> str:
    from pyspark.sql import functions as F

    validate_identifier(catalog)
    audit = spark.table(f"{catalog}.cfihos_trust.merge_audit")
    events = audit.filter(F.col("event_id") == merge_event_id).limit(2).collect()
    if len(events) != 1:
        raise ValueError(f"expected one merge event for {merge_event_id}, found {len(events)}")
    if audit.filter(F.col("reverses_event_id") == merge_event_id).limit(1).count():
        raise ValueError(f"merge event {merge_event_id} is already reversed")
    event = events[0].asDict(recursive=True)
    prior = json.loads(event["prior_state_json"])
    keys = [(row["source_system"], row["entity"], row["source_id"]) for row in prior]
    key_frame = spark.createDataFrame(keys, "source_system string, entity string, source_id string")
    current = [
        row.asDict(recursive=True)
        for row in spark.table(f"{catalog}.cfihos_trust.id_map")
        .join(key_frame, ["source_system", "entity", "source_id"], "inner")
        .collect()
    ]
    restored, reversal = unmerge_state(current, event, actor, reason)
    _apply_id_map_rows(spark, catalog, restored)
    _audit_event(spark, catalog, reversal)
    return reversal["event_id"]
