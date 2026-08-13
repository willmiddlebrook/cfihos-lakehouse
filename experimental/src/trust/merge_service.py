"""Audited merge and unmerge operations for steward-approved identity decisions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def merge_state(
    id_map: list[dict[str, Any]], survivor: str, absorbed: str, actor: str, reason: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if survivor == absorbed:
        raise ValueError("survivor and absorbed identifiers must differ")
    affected = [dict(row) for row in id_map if row["spine_id"] == absorbed]
    if not affected:
        raise ValueError(f"absorbed spine identifier has no mappings: {absorbed}")
    updated = [
        {**row, "spine_id": survivor} if row["spine_id"] == absorbed else dict(row)
        for row in id_map
    ]
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "merge",
        "survivor_spine_id": survivor,
        "absorbed_spine_id": absorbed,
        "prior_state_json": json.dumps(affected, sort_keys=True, default=str),
        "actor": actor,
        "reason": reason,
        "event_at": datetime.now(timezone.utc).isoformat(),
        "reverses_event_id": None,
    }
    return updated, event


def unmerge_state(
    id_map: list[dict[str, Any]], merge_event: dict[str, Any], actor: str, reason: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if merge_event.get("event_type") != "merge":
        raise ValueError("only a merge event can be reversed")
    prior = json.loads(merge_event["prior_state_json"])
    prior_by_key = {(row["source_system"], row["entity"], row["source_id"]): row for row in prior}
    updated = []
    for row in id_map:
        key = (row["source_system"], row["entity"], row["source_id"])
        updated.append(dict(prior_by_key.get(key, row)))
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "unmerge",
        "survivor_spine_id": merge_event["survivor_spine_id"],
        "absorbed_spine_id": merge_event["absorbed_spine_id"],
        "prior_state_json": json.dumps(id_map, sort_keys=True, default=str),
        "actor": actor,
        "reason": reason,
        "event_at": datetime.now(timezone.utc).isoformat(),
        "reverses_event_id": merge_event["event_id"],
    }
    return updated, event
