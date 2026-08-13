# Databricks notebook source
# ruff: noqa: E402, F821
# MAGIC %md
# MAGIC # 04 · Work the “not sure” pile
# MAGIC
# MAGIC Start with [how the system works](../docs/HOW-IT-WORKS.md). The review queue is
# MAGIC the “not sure” pile, and a steward is the named human who resolves it. Exact and
# MAGIC uniquely normalized links are automatic; ambiguous identity decisions are
# MAGIC intentionally human work. Inspect the evidence, choose one explicit action,
# MAGIC and keep the actor and reason in the audit trail.
# MAGIC
# MAGIC Notebook original to this kit. CFIHOS materials © IOGP JIP36, CC BY 4.0.

# COMMAND ----------
import os
import sys
from pathlib import Path

repo_root = Path(os.path.abspath(".."))
sys.path.insert(0, os.path.abspath(".."))

from pyspark.sql import functions as F

from src.identifiers import validate_identifier

dbutils.widgets.text("catalog", "cfihos_tutorial")
dbutils.widgets.dropdown(
    "action",
    "inspect",
    ["inspect", "confirm_to_existing", "confirm_as_new", "reject", "merge", "unmerge"],
)
dbutils.widgets.text("queue_id", "")
dbutils.widgets.text("spine_id", "")
dbutils.widgets.text("survivor_spine_id", "")
dbutils.widgets.text("absorbed_spine_id", "")
dbutils.widgets.text("merge_event_id", "")
dbutils.widgets.text("actor", "")
dbutils.widgets.text("reason", "")

catalog = dbutils.widgets.get("catalog").strip()
action = dbutils.widgets.get("action").strip()
queue_id = dbutils.widgets.get("queue_id").strip()
spine_id = dbutils.widgets.get("spine_id").strip()
survivor_spine_id = dbutils.widgets.get("survivor_spine_id").strip()
absorbed_spine_id = dbutils.widgets.get("absorbed_spine_id").strip()
merge_event_id = dbutils.widgets.get("merge_event_id").strip()
actor = dbutils.widgets.get("actor").strip()
reason = dbutils.widgets.get("reason").strip()
validate_identifier(catalog)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Open review records
# MAGIC
# MAGIC Read the source values, candidate, evidence, and reason before choosing an
# MAGIC action. `confirm_as_new` mints a deterministic spine ID; rerun that source
# MAGIC afterward so its direct mapping can publish claims. Rejection is a decision,
# MAGIC not a snooze, and the record will not requeue.

# COMMAND ----------
review_queue = spark.table(f"{catalog}.cfihos_trust.review_queue")
display(
    review_queue.filter(F.col("status") == "open")
    .select(
        "queue_id",
        "source_system",
        "entity",
        "source_id",
        "candidate_spine_id",
        "reason",
        "evidence",
        "created_at",
    )
    .orderBy("created_at")
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Apply one explicit action
# MAGIC
# MAGIC - **confirm-to-existing (`confirm_to_existing`):** link this source record to a
# MAGIC   real asset already in the registry.
# MAGIC - **confirm-as-new (`confirm_as_new`):** create a new real asset ID, then rerun
# MAGIC   the source so its facts can publish.
# MAGIC - **reject (`reject`):** decide that this source record should not link or
# MAGIC   create; it will not return to the pile on the next run.
# MAGIC - **merge / unmerge:** combine two asset IDs known to mean the same real asset,
# MAGIC   or reverse that audited decision.
# MAGIC
# MAGIC Leave `action=inspect` for a read-only pass. Queue actions require `queue_id`
# MAGIC and the human `actor`; existing confirmation also requires `spine_id`, and
# MAGIC rejection requires `reason`. Merge requires survivor and absorbed spine IDs.
# MAGIC Unmerge requires the merge event ID being reversed.

# COMMAND ----------
from src.trust.steward import (
    apply_merge,
    apply_unmerge,
    confirm_as_new,
    confirm_to_existing,
    reject,
)

result = None
if action != "inspect" and not actor:
    raise ValueError("actor is required for every stewardship action")

if action == "confirm_to_existing":
    if not queue_id or not spine_id:
        raise ValueError("confirm_to_existing requires queue_id and spine_id")
    result = confirm_to_existing(spark, catalog, queue_id, spine_id, actor)
elif action == "confirm_as_new":
    if not queue_id:
        raise ValueError("confirm_as_new requires queue_id")
    result = confirm_as_new(spark, catalog, queue_id, actor)
elif action == "reject":
    if not queue_id or not reason:
        raise ValueError("reject requires queue_id and reason")
    result = reject(spark, catalog, queue_id, actor, reason)
elif action == "merge":
    if not survivor_spine_id or not absorbed_spine_id or not reason:
        raise ValueError("merge requires survivor_spine_id, absorbed_spine_id, and reason")
    result = apply_merge(
        spark,
        catalog,
        survivor_spine_id,
        absorbed_spine_id,
        actor,
        reason,
    )
elif action == "unmerge":
    if not merge_event_id or not reason:
        raise ValueError("unmerge requires merge_event_id and reason")
    result = apply_unmerge(spark, catalog, merge_event_id, actor, reason)
elif action != "inspect":
    raise ValueError(f"unsupported action: {action}")

if result is not None:
    print(result)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Inspect the resulting crosswalk
# MAGIC
# MAGIC Queue actions show the mapping for that source record. Merge actions show the
# MAGIC current mappings associated with either entered spine ID. The append-only
# MAGIC `merge_audit` table retains merge and reversal evidence.

# COMMAND ----------
id_map = spark.table(f"{catalog}.cfihos_trust.id_map")
if queue_id:
    selected_queue = review_queue.filter(F.col("queue_id") == queue_id).select(
        "source_system", "entity", "source_id"
    )
    display(id_map.join(selected_queue, ["source_system", "entity", "source_id"], "inner"))
elif survivor_spine_id or absorbed_spine_id:
    display(
        id_map.filter(F.col("spine_id").isin(survivor_spine_id, absorbed_spine_id)).orderBy(
            "source_system", "entity", "source_id"
        )
    )
elif merge_event_id:
    merge_event = (
        spark.table(f"{catalog}.cfihos_trust.merge_audit")
        .filter(F.col("event_id") == merge_event_id)
        .select("survivor_spine_id", "absorbed_spine_id")
        .first()
    )
    if merge_event is None:
        print(f"No merge event found for {merge_event_id}.")
    else:
        display(
            id_map.filter(
                F.col("spine_id").isin(
                    merge_event.survivor_spine_id,
                    merge_event.absorbed_spine_id,
                )
            ).orderBy("source_system", "entity", "source_id")
        )
else:
    print("Select a queue record or merge action to display resulting ID-map rows.")

# COMMAND ----------
display(
    spark.table(f"{catalog}.cfihos_trust.merge_audit")
    .orderBy(F.desc("event_at"))
    .limit(20)
)

# COMMAND ----------
# MAGIC %md
# MAGIC This notebook is the human gray-zone surface by design. A steward decision is
# MAGIC explicit, attributable, and reversible where applicable; uncertainty is never
# MAGIC converted into an automatic match.
