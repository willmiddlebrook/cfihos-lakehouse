# Databricks notebook source
# ruff: noqa: E402, F821
# MAGIC %md
# MAGIC # 03 · Read the scoreboard
# MAGIC
# MAGIC Start with [how the system works](../docs/HOW-IT-WORKS.md). Health views are
# MAGIC the scoreboard: each governed view below answers one operating question
# MAGIC without hiding the records that still need work.
# MAGIC
# MAGIC Notebook original to this kit. CFIHOS materials © IOGP JIP36, CC BY 4.0.

# COMMAND ----------
import os
import sys
from pathlib import Path

import yaml

repo_root = Path(os.path.abspath(".."))
sys.path.insert(0, os.path.abspath(".."))

from pyspark.sql import functions as F

from src.identifiers import validate_identifier

dbutils.widgets.text("catalog", "cfihos_tutorial")
catalog = dbutils.widgets.get("catalog").strip()
validate_identifier(catalog)

# COMMAND ----------
# MAGIC %md
# MAGIC **For each source, how much linked successfully, how many codes would not
# MAGIC translate, and how deep is the “not sure” pile?**

# COMMAND ----------
display(spark.table(f"{catalog}.cfihos_front_door.source_health").orderBy("source"))

# COMMAND ----------
# MAGIC %md
# MAGIC **For each source, which decision path—founding, exact, normalized, or human
# MAGIC steward—linked its records?**

# COMMAND ----------
display(spark.table(f"{catalog}.cfihos_trust.match_health").orderBy("source", "match_tier"))

# COMMAND ----------
# MAGIC %md
# MAGIC **Which sources and asset types need a human same-asset decision, and how old
# MAGIC is the oldest item in the “not sure” pile?**

# COMMAND ----------
display(
    spark.table(f"{catalog}.cfihos_trust.review_queue_health").orderBy("source", "entity")
)

# COMMAND ----------
# MAGIC %md
# MAGIC **Which source codes have no approved translation into the standard's
# MAGIC vocabulary?**

# COMMAND ----------
display(
    spark.table(f"{catalog}.cfihos_trust.unmapped_code_health").orderBy(
        F.desc("occurrences"), "source", "entity", "attribute"
    )
)

# COMMAND ----------
# MAGIC %md
# MAGIC **Where do source assertions disagree or tie instead of being silently
# MAGIC overwritten?**

# COMMAND ----------
display(
    spark.table(f"{catalog}.cfihos_trust.conflict_health").orderBy(
        F.desc("open_conflicts"), "entity", "attribute"
    )
)

# COMMAND ----------
# MAGIC %md
# MAGIC **Which new assets are withheld because a required value is missing or a value
# MAGIC cannot be cast to the datatype declared by the model?**

# COMMAND ----------
display(spark.table(f"{catalog}.cfihos_trust.pending_health").orderBy("entity"))

# COMMAND ----------
# MAGIC %md
# MAGIC **Did loading the standard's vocabulary lists produce any unexplained rejected
# MAGIC rows?**

# COMMAND ----------
display(
    spark.table(f"{catalog}.cfihos_trust.load_exception_health").orderBy(
        F.desc("unexplained_exceptions"), "file"
    )
)

# COMMAND ----------
# MAGIC %md
# MAGIC **If the executable validator runs now, which data rules pass or fail?**
# MAGIC
# MAGIC The neutral tutorial loads tag and equipment feeds but does not populate the
# MAGIC generated tag-class or equipment-class registry tables. Their foreign-key
# MAGIC checks therefore expose two expected classification gaps; they are evidence to
# MAGIC address, not failures to hide. The official classes remain in `cfihos_ref`.

# COMMAND ----------
from src.validate import validate

model = yaml.safe_load((repo_root / "model" / "model.yml").read_text(encoding="utf-8"))
generation_report = yaml.safe_load(
    (repo_root / "model" / "generation_report.yml").read_text(encoding="utf-8")
)
validation_results = validate(spark, catalog, model, generation_report)
if not validation_results:
    raise RuntimeError("validator returned no checks")
validation_run_id = validation_results[0]["validation_run_id"]
failed_checks = [result for result in validation_results if result["status"] == "FAIL"]
print(f"validation_run_id={validation_run_id}; failed_checks={len(failed_checks)}")

validation = spark.table(f"{catalog}.cfihos_trust.validation_results")
display(
    validation.filter(F.col("validation_run_id") == validation_run_id)
    .select("check_name", "object_name", "failed_rows", "status", "details", "checked_at")
    .orderBy("status", "check_name")
)

# COMMAND ----------
# MAGIC %md
# MAGIC With a founding source run, these views describe a living registry; per-source
# MAGIC standards-gap findings live beside it in the same scoreboard. Configure Genie,
# MAGIC the workspace's natural-language question interface, with
# MAGIC `src/front_door/genie_setup.md`. When the tutorial is complete, drop its catalog.
# MAGIC Open `04_steward.py` to work the human gray zone.
