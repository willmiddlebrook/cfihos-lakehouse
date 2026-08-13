# Databricks notebook source
# ruff: noqa: E402, F821
# MAGIC %md
# MAGIC # 00 · Build the empty filing cabinet
# MAGIC
# MAGIC Start with [how the system works](../docs/HOW-IT-WORKS.md). This creates the
# MAGIC empty filing cabinet and loads the standard's vocabulary lists. A catalog is
# MAGIC the top-level governed container that holds all tutorial tables and views.
# MAGIC Use a **throwaway** catalog, such as `cfihos_tutorial_<name>`.
# MAGIC
# MAGIC The asset tables start empty because the CFIHOS standard supplies structure
# MAGIC and vocabulary, not your organization's asset records. A founding source fills
# MAGIC the first asset list later in notebook 02. This notebook writes only to the
# MAGIC chosen catalog and does not push anything to Git. Drop the catalog when done.
# MAGIC
# MAGIC Notebook original to this kit. CFIHOS materials © IOGP JIP36, CC BY 4.0.

# COMMAND ----------
import os
import sys
from pathlib import Path

repo_root = Path(os.path.abspath(".."))
sys.path.insert(0, os.path.abspath(".."))

from src.identifiers import validate_identifier

dbutils.widgets.text("catalog", "cfihos_tutorial")
catalog = dbutils.widgets.get("catalog").strip()
validate_identifier(catalog)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Create the empty cabinet
# MAGIC
# MAGIC This creates the empty asset tables, decision and audit tables, and scoreboard
# MAGIC views. If `CREATE CATALOG` is forbidden, ask an administrator to pre-create the
# MAGIC catalog and rerun this cell.

# COMMAND ----------
from src.deploy_foundation import deploy

deploy(spark, repo_root, catalog)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Load the standard's vocabulary lists
# MAGIC
# MAGIC The Core Reference Data Library (RDL) contains official class, property, unit,
# MAGIC and document vocabularies. The loader reconciles every source record. Duplicate
# MAGIC natural keys remain visible as explained exceptions instead of disappearing.

# COMMAND ----------
from pyspark.sql import functions as F

from src.load_rdl import load_rdl

load_rdl(spark, repo_root / "spec" / "rdl", catalog, "2.0")

audit = spark.table(f"{catalog}.cfihos_ref.load_audit").filter(
    F.col("rdl_version") == "2.0"
)
actual_counts = []
for row in audit.select("table_name").distinct().collect():
    actual_counts.append(
        (
            row.table_name,
            spark.table(f"{catalog}.cfihos_ref.{row.table_name}")
            .filter(F.col("rdl_version") == "2.0")
            .count(),
        )
    )
actual = spark.createDataFrame(actual_counts, "table_name string, actual_rows long")
display(
    audit.join(actual, "table_name", "left")
    .select(
        "file",
        "table_name",
        "source_rows",
        "loaded_rows",
        "exception_rows",
        "actual_rows",
        "encoding",
    )
    .orderBy("file")
)

# COMMAND ----------
display(
    spark.table(f"{catalog}.cfihos_ref.equipment_class")
    .filter(F.col("rdl_version") == "2.0")
    .select("equipment_class_cfihos_unique_code", "equipment_class_name")
    .orderBy("equipment_class_name")
    .limit(5)
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Create the governed upload parking lot
# MAGIC
# MAGIC A Volume is a governed file folder. Notebook 01 turns a CSV parked here into a
# MAGIC governed Delta table; the source-loading engine consumes tables, not file paths.

# COMMAND ----------
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.cfihos_onramp.uploads")
upload_path = f"/Volumes/{catalog}/cfihos_onramp/uploads"
print(upload_path)

# COMMAND ----------
# MAGIC %md
# MAGIC The empty cabinet and standard vocabulary are now live and queryable. A
# MAGIC **founding source** is the one approved first-census source allowed to create
# MAGIC the initial asset list; run it in notebook 02. Next, open
# MAGIC `01_upload_and_profile.py`.
